#!/usr/bin/env python3
"""
LLM-powered subtitle translation.

This is a *post-processing* stage that runs on a generated SRT — it never
touches the Deepgram transcription path. It parses the source SRT, translates
only the cue text into one or more target languages (in context-batched
windows, with the show's keyterms supplied as glossary), and writes
language-tagged sidecars (``Movie.spa.srt``, ``Movie.fre.srt``, …) that
Plex/Jellyfin/Emby auto-detect.

Two invariants make subtitle translation trustworthy:

1. **Timing is sacrosanct.** Output cues copy the source cues' start/end/index
   verbatim — Nova-3's timestamps stay authoritative. We translate text only.
2. **1:1 cue mapping.** The same number of cues comes out as went in. The LLM
   is asked for a JSON array keyed by index; on any count mismatch we fall back
   to per-cue translation, and an untranslatable cue keeps its source text
   rather than being dropped.

Provider plumbing (incl. local Ollama) and cost live in ``core.llm_providers``.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import srt as srt_lib

from core.llm_providers import LLMModel, LLMProvider, calculate_cost, call_llm
from core.transcribe import (
    _SUBTITLE_LANG_MAP,
    NEUTRAL_SUBTITLE_LANG,
    normalize_language_code,
    resolve_subtitle_language_tag,
)

DEFAULT_WINDOW_SIZE = 30

TRANSLATE_SYSTEM_PROMPT = (
    "You are a professional subtitle translator. You return only a valid JSON "
    "array, preserving every cue's index 1:1. You never merge, split, add, or "
    "drop cues."
)

# Human-readable names for the supported subtitle target codes (keys of
# _SUBTITLE_LANG_MAP). Used to phrase the translation prompt clearly.
_LANGUAGE_NAMES = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "gu": "Gujarati",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ka": "Georgian",
    "kn": "Kannada",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "mr": "Marathi",
    "ms": "Malay",
    "ne": "Nepali",
    "nl": "Dutch",
    "no": "Norwegian",
    "pa": "Punjabi",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sr": "Serbian",
    "sv": "Swedish",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tl": "Tagalog",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh": "Chinese",
}

# Known 3-letter sidecar tags, used to strip a source language tag from a
# subtitle filename (e.g. "Movie.eng.srt" -> media stem "Movie").
_KNOWN_TAGS = set(_SUBTITLE_LANG_MAP.values()) | {NEUTRAL_SUBTITLE_LANG}


@dataclass
class TranslationResult:
    """Outcome of translating one SRT into one target language."""

    cues: List[Any]
    target_tag: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    output_path: Optional[Path] = None
    skipped: bool = False
    metadata: dict = field(default_factory=dict)


# Type of the injectable per-window translator seam.
TextTranslator = Callable[[List[str], str, Optional[List[str]]], Tuple[List[str], int, int]]


class SubtitleTranslator:
    """Translate generated SRT cues into a target language, preserving timing."""

    def __init__(
        self,
        provider: LLMProvider,
        model: Any,
        api_key: Optional[str],
        *,
        ollama_base_url: Optional[str] = None,
        window_size: int = DEFAULT_WINDOW_SIZE,
        text_translator: Optional[TextTranslator] = None,
        llm_call: Callable = call_llm,
    ):
        """
        Args:
            provider: LLM provider (Anthropic/OpenAI/Google/Ollama).
            model: ``LLMModel`` for cloud providers, or a free-text string for Ollama.
            api_key: Provider API key (Ollama ignores it).
            ollama_base_url: Override the Ollama endpoint (``http://host:11434/v1``).
            window_size: How many cues to translate per LLM call.
            text_translator: Override the per-window translator (dependency
                injection for tests). Defaults to the real call_llm-backed one.
            llm_call: Override the LLM dispatch function (used by the default
                translator). Defaults to ``core.llm_providers.call_llm``.
        """
        self.provider = provider
        self.model = model  # kept for cost lookup (enum -> pricing; str -> $0)
        self.model_id = model.value if isinstance(model, LLMModel) else model
        self.api_key = api_key
        self.ollama_base_url = ollama_base_url
        self.window_size = max(1, window_size)
        self._llm_call = llm_call
        self._text_translator = text_translator or self._default_text_translator

    # --- Public API ---------------------------------------------------------

    def translate_cues(
        self,
        cues: List[Any],
        target_language: str,
        keyterms: Optional[List[str]] = None,
    ) -> TranslationResult:
        """Translate a list of srt cues into ``target_language``.

        Returns a TranslationResult whose cues copy the source index/start/end
        verbatim, with only the content translated.
        """
        target_tag = self._resolve_tag(target_language)
        target_name = self._language_name(target_language)

        translated_texts: List[str] = []
        input_tokens = 0
        output_tokens = 0

        for window in _chunk(cues, self.window_size):
            texts = [cue.content for cue in window]
            out_texts, in_tok, out_tok = self._translate_with_retry(texts, target_name, keyterms)
            input_tokens += in_tok
            output_tokens += out_tok
            translated_texts.extend(out_texts)

        new_cues = [
            srt_lib.Subtitle(
                index=cue.index,
                start=cue.start,
                end=cue.end,
                # A blank translation (e.g. the model folded this cue into its
                # neighbour and returned "" for it) falls back to the source
                # text so the cue is never emitted empty — empty-content cues
                # are silently dropped when the sidecar is composed.
                content=text if (text and text.strip()) else cue.content,
                proprietary=cue.proprietary,
            )
            for cue, text in zip(cues, translated_texts)
        ]

        return TranslationResult(
            cues=new_cues,
            target_tag=target_tag,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=calculate_cost(self.model, input_tokens, output_tokens),
        )

    def translate_file(
        self,
        srt_path,
        target_language: str,
        keyterms: Optional[List[str]] = None,
        overwrite: bool = False,
    ) -> TranslationResult:
        """Translate a source SRT file and write a language-tagged sidecar.

        Skips writing (and reading) when the target sidecar already exists,
        unless ``overwrite`` is set.
        """
        srt_path = Path(srt_path)
        target_tag = self._resolve_tag(target_language)  # validate before any I/O
        dest = self._output_path(srt_path, target_tag)

        if dest.exists() and not overwrite:
            return TranslationResult(
                cues=[],
                target_tag=target_tag,
                output_path=dest,
                skipped=True,
            )

        cues = list(srt_lib.parse(srt_path.read_text(encoding="utf-8")))
        result = self.translate_cues(cues, target_language, keyterms=keyterms)
        # reindex=False keeps every cue's index/timing verbatim. The default
        # (reindex=True) runs sort_and_reindex, which silently drops cues with
        # empty content or non-positive duration and renumbers the survivors.
        dest.write_text(srt_lib.compose(result.cues, reindex=False), encoding="utf-8")
        result.output_path = dest
        result.skipped = False
        return result

    # --- Internals ----------------------------------------------------------

    def _resolve_tag(self, target_language: str) -> str:
        """Map a target language code to its 3-letter sidecar tag, or reject it."""
        tag = resolve_subtitle_language_tag(requested_language=target_language)
        if tag == NEUTRAL_SUBTITLE_LANG:
            raise ValueError(
                f"Unsupported target language '{target_language}' — "
                f"no subtitle tag mapping exists for it"
            )
        return tag

    def _language_name(self, code: str) -> str:
        base = (normalize_language_code(code) or code).split("-", 1)[0]
        return _LANGUAGE_NAMES.get(base, code)

    def _output_path(self, srt_path: Path, target_tag: str) -> Path:
        """Derive ``<media-stem>.<target_tag>.srt`` next to the source SRT.

        Strips a source language tag from the stem when present
        (``Movie.eng.srt`` -> ``Movie.spa.srt``); otherwise just appends
        (``Movie.srt`` -> ``Movie.spa.srt``).
        """
        stem = srt_path.stem
        base, dot, last = stem.rpartition(".")
        media_stem = base if (dot and last.lower() in _KNOWN_TAGS) else stem
        return srt_path.parent / f"{media_stem}.{target_tag}.srt"

    def _translate_with_retry(
        self, texts: List[str], target_name: str, keyterms: Optional[List[str]]
    ) -> Tuple[List[str], int, int]:
        """Translate a window, retrying per-cue if the 1:1 mapping breaks."""
        out, in_tok, out_tok = self._text_translator(texts, target_name, keyterms)
        if len(out) == len(texts):
            return out, in_tok, out_tok

        # Count mismatch: translate each cue on its own. A cue that still fails
        # keeps its source text so the output stays 1:1 with the input.
        results: List[str] = []
        total_in, total_out = in_tok, out_tok
        for text in texts:
            single, s_in, s_out = self._text_translator([text], target_name, keyterms)
            total_in += s_in
            total_out += s_out
            results.append(single[0] if len(single) == 1 else text)
        return results, total_in, total_out

    def _default_text_translator(
        self, texts: List[str], target_name: str, keyterms: Optional[List[str]]
    ) -> Tuple[List[str], int, int]:
        """The real per-window translator: build a JSON prompt, call the LLM, parse."""
        prompt = _build_translation_prompt(texts, target_name, keyterms)
        response, in_tok, out_tok = self._llm_call(
            self.provider,
            self.model_id,
            self.api_key,
            prompt,
            max_tokens=_max_tokens_for(texts),
            system_prompt=TRANSLATE_SYSTEM_PROMPT,
            base_url=self.ollama_base_url,
        )
        translated = _parse_translation_response(response, len(texts))
        return translated, in_tok, out_tok


# --- Module-level helpers ---------------------------------------------------


def _chunk(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _max_tokens_for(texts: List[str]) -> int:
    """Heuristic response budget: scales with cue count, floored for Google's
    thinking budget, capped to avoid runaway costs. Tuned during live smoke."""
    return min(8192, max(2048, 512 + len(texts) * 120))


def _build_translation_prompt(
    texts: List[str], target_name: str, keyterms: Optional[List[str]]
) -> str:
    items = [{"i": i, "text": text} for i, text in enumerate(texts)]
    payload = json.dumps(items, ensure_ascii=False)

    keyterm_block = ""
    if keyterms:
        keyterm_block = (
            "Show-specific names and terms — keep these spelled consistently and "
            "do not translate proper nouns unless they have a well-known "
            f"{target_name} form:\n{', '.join(keyterms)}\n\n"
        )

    return (
        f"Translate the subtitle cues below into {target_name}.\n\n"
        f"{keyterm_block}"
        "Rules:\n"
        f'- Translate only the value of each "text" field into {target_name}.\n'
        '- Return ONLY a JSON array of objects {"i": <int>, "text": <string>} '
        "with the SAME indices, same count, same order.\n"
        "- Do not merge, split, add, or drop items. Preserve line breaks within a cue.\n\n"
        f"Input:\n{payload}\n\n"
        "Output (JSON array only):"
    )


def _parse_translation_response(text: str, expected_count: int) -> List[str]:
    """Extract translated cue texts (index-ordered) from an LLM response.

    Tolerates markdown fences and surrounding prose. Returns a best-effort list;
    the caller compares its length against the expected count to decide whether
    a per-cue retry is needed (a wrong-length or empty list signals failure).
    """
    if not text:
        return []

    cleaned = text.strip()
    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```$", "", cleaned)

    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    by_index = {}
    for item in data:
        if isinstance(item, dict) and "i" in item and "text" in item:
            by_index[item["i"]] = str(item["text"])

    return [by_index[i] for i in sorted(by_index)]
