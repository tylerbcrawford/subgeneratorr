#!/usr/bin/env python3
"""
Whisper gap-fill for Deepgram subtitles (experimental, opt-in).

Nova-3 drops shouted or overlapping dialogue under loud music, leaving long
subtitle blanks. When enabled (GAP_FILL=on, -local image only, web/worker
path only - the CLI has no hook), every span of at least GAP_FILL_MIN_SECONDS
with no Deepgram word is checked for speech and, if speech is found,
re-transcribed by the local faster-whisper model; the new cues are merged
into the SRT. Transcript and raw-JSON outputs are built from the Deepgram
response and do not include filled cues.

Deepgram cues are never altered; the file is rewritten only when cues are
added. Any failure leaves the Deepgram SRT as it was. Total decode time per
file is capped at GAP_FILL_BUDGET_SECONDS.

Two different uses of Silero VAD:
- As Whisper's internal ``vad_filter`` it trims speech under a music bed, so
  decoding runs with it off.
- As a yes/no pre-check ("at least SPEECH_MIN_SECONDS of speech anywhere in
  this blank?") it reliably separates speech-bearing blanks from pure music or
  silence, because loud speech still registers even when the bed around it
  does not.

Evaluated on 40 blanks from 4 files against official subtitles (in-sample):
the pre-check cut decode time 82%; with the 0.5 word-probability floor, 23
correct cues were added vs 26 untuned, and wrong cues fell from 11 to 3.
Recall of missed dialogue is about 25%. Show keyterms are not passed as
hotwords: +60% decode time for ~2 points of recall, and they seeded
hallucinations ("hack, hack, hack") in speechless windows.
"""

import io
import logging
import os
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import srt as srt_lib

from core.asr_engine import (
    NormalizedSegment,
    NormalizedWord,
    WhisperEngine,
    _parse_replace_pairs,
    whisper_available,
)
from core.languages import whisper_language_code
from core.srt_writer import MIN_CUE_SECONDS, _chunk_worded_segment

logger = logging.getLogger(__name__)

EDGE_MARGIN = 0.2  # keep filled words this far from neighbouring Deepgram words
MAX_NO_SPEECH_PROB = 0.6
MIN_AVG_LOGPROB = -1.0
MAX_COMPRESSION_RATIO = 2.4
MIN_MEAN_WORD_PROB = 0.5
SPEECH_VAD_THRESHOLD = 0.5
SPEECH_MIN_SECONDS = 2.0
try:
    GAP_FILL_BUDGET_SECONDS = max(60, int(os.environ.get("GAP_FILL_BUDGET_SECONDS", "600")))
except ValueError:
    GAP_FILL_BUDGET_SECONDS = 600
_HALLUCINATIONS = {
    "thank you.",
    "thanks for watching!",
    "thanks for watching.",
    "you",
    "♪",
    "...",
    "subtitles by the amara.org community",
}


def gap_fill_enabled() -> bool:
    return os.environ.get("GAP_FILL", "off").strip().lower() in ("on", "1", "true", "yes")


def min_gap_seconds() -> float:
    try:
        return max(2.0, float(os.environ.get("GAP_FILL_MIN_SECONDS", "10")))
    except ValueError:
        return 10.0


def should_gap_fill(
    *,
    engine: str,
    language: Optional[str],
    detect_language: bool,
    profanity_filter: str,
    redact,
    multichannel: bool,
    speaker_labels: bool = False,
) -> Tuple[bool, str]:
    """Return (run, reason). Whisper text cannot honour Deepgram-only options."""
    if not gap_fill_enabled():
        return False, "disabled"
    if engine == "whisper":
        return False, "whisper engine"
    if not whisper_available():
        return False, "faster-whisper not installed"
    if detect_language or not language or language == "multi":
        return False, "language not fixed"
    if profanity_filter and profanity_filter != "off":
        return False, "profanity filter on"
    if redact:
        return False, "redaction on"
    if multichannel:
        return False, "multichannel"
    if speaker_labels:
        return False, "speaker labels on"
    return True, "ok"


def find_gaps(word_times: List[Tuple[float, float]], duration: float, min_gap: float):
    """Spans >= min_gap with no word, including head and tail of the file."""
    gaps = []
    cursor = 0.0
    for start, end in sorted(word_times):
        if start - cursor >= min_gap:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor >= min_gap:
        gaps.append((cursor, duration))
    return gaps


def deepgram_word_times(resp) -> List[Tuple[float, float]]:
    try:
        words = resp.results.channels[0].alternatives[0].words or []
    except (AttributeError, IndexError):
        return []
    return [(float(w.start), float(w.end)) for w in words]


def _probe_duration(audio: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(audio),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return float(out.stdout.strip() or 0)


def _slice(audio: Path, start: float, length: float) -> bytes:
    out = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{length:.3f}",
            "-i",
            str(audio),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "flac",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=600,
    )
    return out.stdout


def speech_seconds(buf: bytes) -> float:
    """Seconds of speech Silero VAD finds in an audio slice."""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    pcm = decode_audio(io.BytesIO(buf), sampling_rate=16000)
    stamps = get_speech_timestamps(
        pcm, VadOptions(threshold=SPEECH_VAD_THRESHOLD, min_silence_duration_ms=500)
    )
    return sum(x["end"] - x["start"] for x in stamps) / 16000


def _segment_ok(seg) -> bool:
    words = seg.words or []
    if not words:
        return False
    if seg.text.strip().lower() in _HALLUCINATIONS:
        return False
    if seg.no_speech_prob > MAX_NO_SPEECH_PROB and seg.avg_logprob < MIN_AVG_LOGPROB:
        return False
    if seg.avg_logprob < MIN_AVG_LOGPROB - 0.5 or seg.compression_ratio > MAX_COMPRESSION_RATIO:
        return False
    return sum(w.probability for w in words) / len(words) >= MIN_MEAN_WORD_PROB


def transcribe_gap(
    model, buf: bytes, offset: float, lo: float, hi: float, language: str
) -> List[NormalizedSegment]:
    segments, _ = model.transcribe(
        io.BytesIO(buf),
        language=language,
        word_timestamps=True,
        vad_filter=False,
        condition_on_previous_text=False,
        hallucination_silence_threshold=2,
    )
    out = []
    for seg in segments:
        if not _segment_ok(seg):
            continue
        words = [
            NormalizedWord(word=w.word.strip(), start=w.start + offset, end=w.end + offset)
            for w in seg.words
            if w.word.strip() and lo <= w.start + offset and w.end + offset <= hi
        ]
        if words:
            out.append(
                NormalizedSegment(
                    start=words[0].start,
                    end=words[-1].end,
                    text=" ".join(w.word for w in words),
                    words=words,
                )
            )
    return out


def _apply_replace(text: str, replace) -> str:
    for wrong, right in _parse_replace_pairs(replace) or []:
        text = text.replace(wrong, right)
    return text


def gap_fill_srt(
    srt_path: Path,
    audio_path: Path,
    resp,
    language: str,
    replace=None,
    progress=None,
) -> int:
    """Fill Deepgram blanks with Whisper cues in place. Returns cues added (0 on failure)."""
    try:
        duration = _probe_duration(audio_path)
        gaps = find_gaps(deepgram_word_times(resp), duration, min_gap_seconds())
        if not gaps:
            return 0
        model = WhisperEngine()._load_model()
        lang = whisper_language_code(language)
        new_cues = []
        started = time.monotonic()
        for i, (g0, g1) in enumerate(gaps):
            if progress:
                progress(i, len(gaps))
            if time.monotonic() - started > GAP_FILL_BUDGET_SECONDS:
                logger.warning(
                    "Gap-fill budget (%ss) spent; %d blank(s) left unfilled",
                    GAP_FILL_BUDGET_SECONDS,
                    len(gaps) - i,
                )
                break
            lo, hi = g0 + (EDGE_MARGIN if g0 > 0 else 0), g1 - (EDGE_MARGIN if g1 < duration else 0)
            try:
                buf = _slice(audio_path, g0, g1 - g0)
                speech = speech_seconds(buf)
                if speech < SPEECH_MIN_SECONDS:
                    logger.info("Gap-fill %.1f-%.1fs: no speech (%.1fs), skipped", g0, g1, speech)
                    continue
                segs = transcribe_gap(model, buf, g0, lo, hi, lang)
                cues = [c for s in segs for c in _chunk_worded_segment(s)]
            except Exception as e:  # one bad gap must not lose the others
                logger.warning("Gap-fill %.1f-%.1fs failed: %s", g0, g1, e)
                continue
            for j, c in enumerate(cues):
                limit = cues[j + 1].start if j + 1 < len(cues) else hi
                c.end = min(max(c.end, c.start + MIN_CUE_SECONDS), limit)
                if c.end > c.start:
                    new_cues.append(c)
            logger.info("Gap-fill %.1f-%.1fs: %d cue(s)", g0, g1, len(cues))
        if not new_cues:
            return 0
        existing = list(srt_lib.parse(srt_path.read_text(encoding="utf-8")))
        existing += [
            srt_lib.Subtitle(
                index=0,
                start=timedelta(seconds=c.start),
                end=timedelta(seconds=c.end),
                content=_apply_replace(c.text, replace),
            )
            for c in new_cues
        ]
        srt_path.write_text(srt_lib.compose(existing, reindex=True), encoding="utf-8")
        return len(new_cues)
    except Exception as e:
        logger.warning("Gap-fill skipped for %s: %s", srt_path.name, e)
        return 0
