#!/usr/bin/env python3
"""
Native SRT writer for normalized ASR results (the local Whisper path).

Whisper emits sentence-length segments — frequently longer than 7 seconds and
84 characters — which are unreadable as subtitle cues verbatim. On the cloud
path this re-chunking is done implicitly by ``deepgram_captions``; here it is
explicit policy, applied to word timestamps:

- max ``MAX_LINES`` lines of ``MAX_LINE_CHARS`` characters per cue
- max cue duration ``MAX_CUE_SECONDS``; cues shorter than ``MIN_CUE_SECONDS``
  are extended (never past the next cue's start)
- cues split at sentence-final punctuation and at silence gaps longer than
  ``GAP_SPLIT_SECONDS``

The Deepgram path keeps its existing ``deepgram_captions`` writer — this
module must never be wired into it (cloud byte output stays unchanged).
"""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

import srt as srt_lib

from core.asr_engine import NormalizedResult, NormalizedSegment

MAX_LINE_CHARS = 42
MAX_LINES = 2
MAX_CUE_SECONDS = 7.0
MIN_CUE_SECONDS = 1.0
GAP_SPLIT_SECONDS = 1.0

_SENTENCE_END = (".", "?", "!", "…")
_TRAILING_QUOTES = "\"'”’»)]"


@dataclass
class _Cue:
    start: float
    end: float
    text: str


def _ends_sentence(word: str) -> bool:
    return word.rstrip(_TRAILING_QUOTES).endswith(_SENTENCE_END)


def _layout_lines(text: str) -> List[str]:
    """Greedy word wrap at MAX_LINE_CHARS; an over-long word gets its own line."""
    lines = []
    current = ""
    for word in text.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= MAX_LINE_CHARS:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _chunk_worded_segment(segment: NormalizedSegment) -> List[_Cue]:
    cues = []
    current = []

    def flush():
        if current:
            text = " ".join(w.word for w in current).strip()
            if text:
                cues.append(_Cue(start=current[0].start, end=current[-1].end, text=text))
            current.clear()

    for word in segment.words:
        if current:
            gap = word.start - current[-1].end
            duration = word.end - current[0].start
            candidate = " ".join(w.word for w in current) + " " + word.word
            if (
                gap > GAP_SPLIT_SECONDS
                or duration > MAX_CUE_SECONDS
                or len(_layout_lines(candidate)) > MAX_LINES
            ):
                flush()
        current.append(word)
        if _ends_sentence(word.word):
            flush()
    flush()
    return cues


def _chunk_wordless_segment(segment: NormalizedSegment) -> List[_Cue]:
    """No word timestamps: wrap text, pair lines into cues, time proportionally."""
    lines = _layout_lines(segment.text)
    if not lines:
        return []
    chunks = [" ".join(lines[i : i + MAX_LINES]) for i in range(0, len(lines), MAX_LINES)]
    total_chars = sum(len(c) for c in chunks)
    duration = max(segment.end - segment.start, 0.0)

    cues = []
    cursor = segment.start
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            end = segment.end  # pin the last chunk to avoid float drift
        else:
            end = cursor + duration * (len(chunk) / total_chars)
        cues.append(_Cue(start=cursor, end=end, text=chunk))
        cursor = end
    return cues


def _enforce_min_duration(cues: List[_Cue]) -> None:
    for i, cue in enumerate(cues):
        if cue.end - cue.start < MIN_CUE_SECONDS:
            extended = cue.start + MIN_CUE_SECONDS
            if i + 1 < len(cues):
                extended = min(extended, cues[i + 1].start)
            cue.end = max(cue.end, extended)


def build_srt(result: NormalizedResult) -> str:
    """Compose SRT text from a NormalizedResult, applying the cue policy."""
    cues = []
    for segment in result.segments:
        if segment.words:
            cues.extend(_chunk_worded_segment(segment))
        elif segment.text.strip():
            cues.extend(_chunk_wordless_segment(segment))

    if not cues:
        raise ValueError(
            "No speech detected in audio — the local engine returned an empty "
            "transcript. Skipping SRT generation."
        )

    _enforce_min_duration(cues)

    subs = [
        srt_lib.Subtitle(
            index=i,
            start=timedelta(seconds=cue.start),
            end=timedelta(seconds=cue.end),
            content="\n".join(_layout_lines(cue.text)),
        )
        for i, cue in enumerate(cues, start=1)
    ]
    return srt_lib.compose(subs)


def write_normalized_transcript(result: NormalizedResult, dest: Path) -> Optional[Path]:
    """
    Write a plain-text transcript from normalized segments (whisper path).

    The local engine has no diarization, so there are no speaker labels —
    segment texts are written paragraph-per-segment. Mirrors write_transcript's
    no-raise contract on empty input (log and return None).
    """
    texts = [seg.text.strip() for seg in result.segments if seg.text.strip()]
    if not texts:
        import logging

        logging.getLogger(__name__).warning(
            "No speech detected — skipping transcript generation for: %s", dest.name
        )
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n\n".join(texts), encoding="utf-8")
    return dest


def write_normalized_srt(
    result: NormalizedResult, dest: Path, lang: Optional[str] = None
) -> Path:
    """
    Write SRT from a NormalizedResult, mirroring write_srt()'s path contract:
    when a language tag is given, the destination is forced to `.{lang}.srt`.

    Returns the path actually written.
    """
    if lang and not dest.name.endswith(f".{lang}.srt"):
        dest = dest.parent / f"{dest.stem}.{lang}.srt"
    dest.write_text(build_srt(result), encoding="utf-8")
    return dest
