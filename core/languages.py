"""
Single source of truth for every language the UI can offer.

Each entry records which engines can transcribe it (Deepgram Nova-3, local
Whisper) and whether it is offered as a translation target. The web UI renders
its dropdowns from ``catalog_payload()`` (served by ``GET /api/languages``) so
adding a language is a one-line change here plus its subtitle tag in
``core/transcribe.py`` (the lockstep tests enforce both).
"""

from dataclasses import asdict, dataclass
from typing import Dict, List

# Display names for base language codes. Keys must match _SUBTITLE_LANG_MAP and
# _STREAM_LANG_MAP in core/transcribe.py (tests/test_language_pipeline.py).
LANGUAGE_NAMES = {
    "af": "Afrikaans",
    "am": "Amharic",
    "ar": "Arabic",
    "as": "Assamese",
    "az": "Azerbaijani",
    "ba": "Bashkir",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bo": "Tibetan",
    "br": "Breton",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fo": "Faroese",
    "fr": "French",
    "gl": "Galician",
    "gu": "Gujarati",
    "ha": "Hausa",
    "haw": "Hawaiian",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "ht": "Haitian Creole",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "jv": "Javanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "la": "Latin",
    "lb": "Luxembourgish",
    "ln": "Lingala",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mg": "Malagasy",
    "mi": "Maori",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Burmese",
    "ne": "Nepali",
    "nl": "Dutch",
    "nn": "Norwegian Nynorsk",
    "no": "Norwegian",
    "oc": "Occitan",
    "pa": "Punjabi",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sa": "Sanskrit",
    "sd": "Sindhi",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sn": "Shona",
    "so": "Somali",
    "sq": "Albanian",
    "sr": "Serbian",
    "su": "Sundanese",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "tk": "Turkmen",
    "tl": "Tagalog",
    "tr": "Turkish",
    "tt": "Tatar",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "zh": "Chinese",
}

# Base codes Deepgram Nova-3 transcribes (https://developers.deepgram.com/docs/models-languages-overview).
DEEPGRAM_BASE_LANGUAGES = frozenset(
    """af ar as be bg bn bs ca cs da de el en es et fa fi fr gu he hi hr hu hy id it ja
    ka kk kn ko lt lv mk mn mr ms ne nl no pa pl ps pt ro ru sk sl sr sv ta te th tl tr
    uk ur vi zh""".split()
)

# Nova-3 regional variants, in display order. Whisper has no regional models, so
# these are Cloud-only (the local engine folds a region to its base code).
DEEPGRAM_REGIONAL_VARIANTS = [
    ("ar-AE", "Arabic (UAE)"),
    ("ar-DZ", "Arabic (Algeria)"),
    ("ar-EG", "Arabic (Egypt)"),
    ("ar-IQ", "Arabic (Iraq)"),
    ("ar-IR", "Arabic (Iran)"),
    ("ar-JO", "Arabic (Jordan)"),
    ("ar-KW", "Arabic (Kuwait)"),
    ("ar-LB", "Arabic (Lebanon)"),
    ("ar-MA", "Arabic (Morocco)"),
    ("ar-PS", "Arabic (Palestine)"),
    ("ar-QA", "Arabic (Qatar)"),
    ("ar-SA", "Arabic (Saudi Arabia)"),
    ("ar-SD", "Arabic (Sudan)"),
    ("ar-SY", "Arabic (Syria)"),
    ("ar-TD", "Arabic (Chad)"),
    ("ar-TN", "Arabic (Tunisia)"),
    ("zh-Hant", "Chinese (Traditional)"),
    ("zh-HK", "Chinese (Cantonese)"),
    ("da-DK", "Danish (Denmark)"),
    ("nl-BE", "Dutch (Belgium)"),
    ("en-AU", "English (Australia)"),
    ("en-GB", "English (UK)"),
    ("en-IN", "English (India)"),
    ("en-NZ", "English (New Zealand)"),
    ("en-US", "English (US)"),
    ("fr-CA", "French (Canada)"),
    ("de-CH", "German (Switzerland)"),
    ("ko-KR", "Korean (Korea)"),
    ("pt-BR", "Portuguese (Brazil)"),
    ("pt-PT", "Portuguese (Portugal)"),
    ("es-419", "Spanish (Latin America)"),
    ("sv-SE", "Swedish (Sweden)"),
]

# faster-whisper transcribes every base language above (openai/whisper's
# LANGUAGES table minus Cantonese "yue", which only large-v3 knows).
WHISPER_LANGUAGES = frozenset(LANGUAGE_NAMES)

# Whisper's own code differs from ISO 639-1 for Javanese.
WHISPER_CODE_ALIASES = {"jv": "jw"}

# Dropdown labels that differ from the plain language name.
_DISPLAY_NAMES = {"zh": "Chinese (Simplified)"}

# English is the usual source language, so it is not offered as a target.
_NON_TARGETS = {"en"}


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    base: str
    deepgram: bool
    whisper: bool
    translate: bool
    special: bool = False  # auto-detect / multi-language pseudo-entries


def _build() -> List[Language]:
    specials = [
        Language("auto", "Auto-detect", "auto", True, True, False, special=True),
        Language("multi", "Multi-language", "multi", True, False, False, special=True),
    ]
    entries = [
        Language(
            code,
            _DISPLAY_NAMES.get(code, name),
            code,
            deepgram=code in DEEPGRAM_BASE_LANGUAGES,
            whisper=code in WHISPER_LANGUAGES,
            translate=code not in _NON_TARGETS,
        )
        for code, name in LANGUAGE_NAMES.items()
    ]
    entries += [
        Language(code, name, code.split("-", 1)[0], True, False, False)
        for code, name in DEEPGRAM_REGIONAL_VARIANTS
    ]
    entries.sort(key=lambda lang: lang.name.lower())
    return specials + entries


LANGUAGES: List[Language] = _build()
LANGUAGES_BY_CODE: Dict[str, Language] = {lang.code: lang for lang in LANGUAGES}

TRANSCRIPTION_CODES = frozenset(lang.code for lang in LANGUAGES if lang.deepgram or lang.whisper)
TRANSLATION_CODES = frozenset(lang.code for lang in LANGUAGES if lang.translate)


def whisper_language_code(code: str) -> str:
    """Map a catalog code to the code faster-whisper expects."""
    base = code.split("-", 1)[0]
    return WHISPER_CODE_ALIASES.get(base, base)


def catalog_language_code(whisper_code: str) -> str:
    """Inverse of ``whisper_language_code`` for detected-language results."""
    for catalog, whisper in WHISPER_CODE_ALIASES.items():
        if whisper_code == whisper:
            return catalog
    return whisper_code


def catalog_payload() -> List[dict]:
    """JSON-ready catalog: specials first, then entries sorted by name."""
    return [asdict(lang) for lang in LANGUAGES]
