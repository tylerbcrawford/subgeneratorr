#!/usr/bin/env python3
"""
Pluggable ASR engine layer for Subgeneratorr.

Defines the engine-agnostic transcription interface (v3.0.0 local engine):

- ``TranscribeOptions`` / ``NormalizedResult`` — the request/response contract
  shared by every engine.
- ``DeepgramEngine`` — wraps the existing ``core.transcribe.transcribe_file``
  cloud path. The web pipeline keeps consuming the raw Deepgram response (and
  its proven ``deepgram_captions`` SRT writer) so cloud output is unchanged;
  the wrapper exists for capability declaration, the CLI, and normalization.
- ``WhisperEngine`` — local CPU transcription via faster-whisper. The import
  is lazy: the lean default image does not ship faster-whisper, only the
  ``-local`` image does.

Capability constants drive the Web UI's option gating (``/api/capabilities``):
controls tagged with a capability the active engine lacks are hidden.
"""

import importlib.util
import io
import logging
import os
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Capability vocabulary (single source of truth for UI gating)
# --------------------------------------------------------------------------

CAP_KEYTERM = "keyterm"
CAP_AUDIO_INTELLIGENCE = "audio_intelligence"
CAP_REDACTION = "redaction"
CAP_DIARIZATION = "diarization"
CAP_SMART_FORMAT = "smart_format"
CAP_MULTICHANNEL = "multichannel"
CAP_UTTERANCES = "utterances"
CAP_PROFANITY_FILTER = "profanity_filter"
CAP_FIND_REPLACE = "find_replace"
CAP_LANGUAGE_DETECT = "language_detect"

VALID_ENGINES = {"deepgram", "whisper"}
DEFAULT_ENGINE = "deepgram"

# Whisper keyterm biasing is best-effort: hotwords share the model's prompt
# window, and overstuffing it degrades output and invites hallucination.
WHISPER_MAX_KEYTERMS = 32
WHISPER_MAX_HOTWORD_CHARS = 500

DEFAULT_WHISPER_MODEL = "small"
ALLOWED_WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")

# At most ONE loaded model per worker process: repeat jobs reuse the instance
# (load costs seconds + hundreds of MB), and switching models evicts the old
# one first — keeping every size ever selected would blow the worker's memory
# limit (small + medium + large-v3 ≈ 5 GB against a 4 GB cap).
_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()


def whisper_available() -> bool:
    """True when faster-whisper is installed (the -local images only)."""
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except ValueError:
        # find_spec raises for a sys.modules entry with __spec__ = None
        # (e.g. a test stub) — the import would still succeed.
        return "faster_whisper" in sys.modules


def deepgram_available() -> bool:
    """True when a Deepgram API key is configured — the cloud engine is
    unusable without one, so a zero-cloud deploy must not advertise it."""
    return bool(os.environ.get("DEEPGRAM_API_KEY"))


def default_engine() -> str:
    """Engine for requests that omit `engine`: ASR_ENGINE env, validated."""
    name = os.environ.get("ASR_ENGINE", DEFAULT_ENGINE)
    if name not in VALID_ENGINES:
        logger.warning("Invalid ASR_ENGINE %r — using %r", name, DEFAULT_ENGINE)
        return DEFAULT_ENGINE
    return name


# --------------------------------------------------------------------------
# Request / response contract
# --------------------------------------------------------------------------


@dataclass
class TranscribeOptions:
    """Engine-agnostic transcription options; engines ignore what they can't use."""

    language: str = "en"
    detect_language: bool = False
    keyterms: Optional[List[str]] = None
    replace: Optional[List[str]] = None  # "wrong:right" pairs
    model: Optional[str] = None  # engine-specific model override


@dataclass
class NormalizedWord:
    word: str
    start: float
    end: float
    speaker: Optional[int] = None


@dataclass
class NormalizedSegment:
    start: float
    end: float
    text: str
    words: List[NormalizedWord] = field(default_factory=list)


@dataclass
class NormalizedResult:
    segments: List[NormalizedSegment] = field(default_factory=list)
    detected_language: Optional[str] = None
    raw: Optional[object] = None  # provider-native response, when available


ProgressCallback = Callable[[float, float], None]  # (seconds_done, total_seconds)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def cap_keyterms(keyterms: Optional[List[str]]) -> Optional[str]:
    """Join keyterms into a hotwords string, capped by count and length."""
    if not keyterms:
        return None
    capped = list(keyterms[:WHISPER_MAX_KEYTERMS])
    joined = ", ".join(capped)
    while capped and len(joined) > WHISPER_MAX_HOTWORD_CHARS:
        capped.pop()
        joined = ", ".join(capped)
    return joined or None


def _parse_replace_pairs(replace: Optional[List[str]]):
    pairs = []
    for item in replace or []:
        if ":" in item:
            wrong, right = item.split(":", 1)
            if wrong:
                pairs.append((wrong, right))
    return pairs


def _apply_replacements(result: NormalizedResult, replace: Optional[List[str]]):
    pairs = _parse_replace_pairs(replace)
    if not pairs:
        return result
    for seg in result.segments:
        for wrong, right in pairs:
            seg.text = seg.text.replace(wrong, right)
        for w in seg.words:
            for wrong, right in pairs:
                w.word = w.word.replace(wrong, right)
    return result


# --------------------------------------------------------------------------
# Engine interface
# --------------------------------------------------------------------------


class ASREngine(ABC):
    """A speech-to-text engine producing normalized segment/word output."""

    name: str = ""

    @classmethod
    @abstractmethod
    def capabilities(cls) -> set:
        """Capability constants this engine supports (drives UI gating)."""

    @classmethod
    def is_available(cls) -> bool:
        """Whether this engine can actually run in the current image."""
        return True

    @abstractmethod
    def transcribe(
        self,
        buf: bytes,
        opts: TranscribeOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> NormalizedResult:
        """Transcribe an audio buffer to a NormalizedResult."""


class DeepgramEngine(ASREngine):
    """Cloud Deepgram Nova-3 engine (the default)."""

    name = "deepgram"

    def __init__(self, api_key: Optional[str] = None, model: str = "nova-3"):
        self.api_key = api_key if api_key is not None else os.environ.get("DEEPGRAM_API_KEY", "")
        self.model = model

    @classmethod
    def is_available(cls) -> bool:
        return deepgram_available()

    @classmethod
    def capabilities(cls) -> set:
        return {
            CAP_KEYTERM,
            CAP_AUDIO_INTELLIGENCE,
            CAP_REDACTION,
            CAP_DIARIZATION,
            CAP_SMART_FORMAT,
            CAP_MULTICHANNEL,
            CAP_UTTERANCES,
            CAP_PROFANITY_FILTER,
            CAP_FIND_REPLACE,
            CAP_LANGUAGE_DETECT,
        }

    def transcribe(
        self,
        buf: bytes,
        opts: TranscribeOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> NormalizedResult:
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not set — configure it in .env")
        from core.transcribe import transcribe_file

        resp = transcribe_file(
            buf,
            self.api_key,
            opts.model or self.model,
            opts.language,
            keyterms=opts.keyterms,
            detect_language=opts.detect_language,
            replace=opts.replace,
        )
        return self.normalize_response(resp)

    @staticmethod
    def normalize_response(resp) -> NormalizedResult:
        """Adapt a Deepgram response to NormalizedResult (utterance-based)."""
        segments = []
        try:
            utterances = resp.results.utterances or []
        except AttributeError:
            utterances = []
        for utt in utterances:
            words = [
                NormalizedWord(
                    word=getattr(w, "punctuated_word", None) or w.word,
                    start=w.start,
                    end=w.end,
                    speaker=getattr(w, "speaker", None),
                )
                for w in (utt.words or [])
            ]
            segments.append(
                NormalizedSegment(start=utt.start, end=utt.end, text=utt.transcript, words=words)
            )
        try:
            detected = resp.results.channels[0].detected_language
        except (AttributeError, IndexError):
            detected = None
        return NormalizedResult(segments=segments, detected_language=detected, raw=resp)


class WhisperEngine(ASREngine):
    """Local faster-whisper engine (CPU, int8). Ships only in the -local image."""

    name = "whisper"

    def __init__(
        self,
        model: Optional[str] = None,
        model_dir: Optional[str] = None,
        compute_type: Optional[str] = None,
        cpu_threads: Optional[int] = None,
    ):
        self.model = model or os.environ.get("WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
        if self.model not in ALLOWED_WHISPER_MODELS:
            raise ValueError(
                f"Unsupported whisper model {self.model!r}; "
                f"expected one of {', '.join(ALLOWED_WHISPER_MODELS)}"
            )
        self.model_dir = model_dir or os.environ.get("WHISPER_MODEL_DIR") or None
        self.compute_type = compute_type or os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
        self.cpu_threads = (
            cpu_threads
            if cpu_threads is not None
            else int(os.environ.get("WHISPER_CPU_THREADS", "0"))
        )

    @classmethod
    def capabilities(cls) -> set:
        # Keyterms map to hotwords — best-effort, weaker than Nova-3 keyterm
        # prompting. Find & replace is post-processing. Everything else in the
        # vocabulary is Deepgram-only and gated off in the UI.
        return {CAP_KEYTERM, CAP_FIND_REPLACE, CAP_LANGUAGE_DETECT}

    @classmethod
    def is_available(cls) -> bool:
        # The lean default image does not ship faster-whisper; advertising the
        # engine there would let jobs fail mid-worker instead of at submit.
        return whisper_available()

    def _load_model(self):
        key = (self.model, self.compute_type, self.model_dir, self.cpu_threads)
        with _MODEL_CACHE_LOCK:
            cached = _MODEL_CACHE.get(key)
            if cached is not None:
                return cached
            # Lazy import: the lean image does not ship faster-whisper.
            from faster_whisper import WhisperModel

            if _MODEL_CACHE:
                logger.info(
                    "Evicting cached whisper model(s) %s before loading %s",
                    [k[0] for k in _MODEL_CACHE],
                    self.model,
                )
                _MODEL_CACHE.clear()
            logger.info(
                "Loading whisper model %s (compute=%s, dir=%s)",
                self.model,
                self.compute_type,
                self.model_dir or "<default cache>",
            )
            instance = WhisperModel(
                self.model,
                device="cpu",
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
                download_root=self.model_dir,
            )
            _MODEL_CACHE[key] = instance
            return instance

    def transcribe(
        self,
        buf: bytes,
        opts: TranscribeOptions,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> NormalizedResult:
        model = self._load_model()

        # Deepgram's multilingual code-switching mode ("multi") has no Whisper
        # equivalent; auto-detect is the closest behavior. Regional variants
        # ("pt-BR") normalize to base codes — whisper rejects them.
        if opts.detect_language or opts.language == "multi" or not opts.language:
            language = None
        else:
            language = opts.language.split("-", 1)[0]

        segments_iter, info = model.transcribe(
            io.BytesIO(buf),
            language=language,
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
            hotwords=cap_keyterms(opts.keyterms),
        )

        total = getattr(info, "duration", 0.0) or 0.0
        segments = []
        for seg in segments_iter:
            words = [
                NormalizedWord(word=w.word.strip(), start=w.start, end=w.end)
                for w in (seg.words or [])
            ]
            segments.append(
                NormalizedSegment(start=seg.start, end=seg.end, text=seg.text.strip(), words=words)
            )
            if progress_callback is not None:
                progress_callback(seg.end, total)

        result = NormalizedResult(
            segments=segments, detected_language=getattr(info, "language", None)
        )
        return _apply_replacements(result, opts.replace)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

ENGINES = {
    DeepgramEngine.name: DeepgramEngine,
    WhisperEngine.name: WhisperEngine,
}


def get_engine(name: str, **kwargs) -> ASREngine:
    """Instantiate an engine by name; raises ValueError for unknown names."""
    cls = ENGINES.get(name)
    if cls is None:
        raise ValueError(f"Unknown ASR engine {name!r}; expected one of {sorted(ENGINES)}")
    return cls(**kwargs)


def engine_capabilities() -> dict:
    """JSON-friendly capability map for /api/capabilities."""
    return {
        name: {"capabilities": sorted(cls.capabilities()), "available": cls.is_available()}
        for name, cls in ENGINES.items()
    }
