"""Tests for the shared language catalog (core/languages.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.languages import (  # noqa: E402
    DEEPGRAM_BASE_LANGUAGES,
    LANGUAGE_NAMES,
    LANGUAGES,
    LANGUAGES_BY_CODE,
    TRANSLATION_CODES,
    catalog_language_code,
    catalog_payload,
    whisper_language_code,
)

# openai/whisper tokenizer LANGUAGES (Whisper spells Javanese "jw"); "yue" is
# deliberately excluded (large-v3 only).
_OPENAI_WHISPER_CODES = set(
    """en zh de es ru ko fr ja pt tr pl ca nl ar sv it id hi fi vi he uk el ms cs ro da
    hu ta no th ur hr bg lt la mi ml cy sk te fa lv bn sr az sl kn et mk br eu is hy ne
    mn bs kk sq sw gl mr pa si km sn yo so af oc ka be tg sd gu am yi lo uz fo ht ps tk
    nn mt sa lb my bo tl mg as tt haw ln ha ba jw su""".split()
)

# The Nova-3 dropdown before the catalog existed (web/templates/index.html, v3.2.0).
_V32_DROPDOWN = set(
    """en auto multi af ar ar-AE ar-DZ ar-EG ar-IQ ar-IR ar-JO ar-KW ar-LB ar-MA ar-PS
    ar-QA ar-SA ar-SD ar-SY ar-TD ar-TN hy as be bn bs bg ca zh zh-Hant zh-HK hr cs da
    da-DK nl nl-BE en-AU en-GB en-IN en-NZ en-US et fa fi fr fr-CA ka de de-CH el gu he
    hi hu id it ja kn kk ko ko-KR lv lt mk ms mr mn ne no ps pl pt pt-BR pt-PT pa ro ru
    sr sk sl es es-419 sv sv-SE tl ta te th tr uk ur vi""".split()
)


def test_base_languages_match_subtitle_tag_map():
    from core.transcribe import _SUBTITLE_LANG_MAP

    assert set(LANGUAGE_NAMES) == set(_SUBTITLE_LANG_MAP)


def test_deepgram_entries_are_exactly_the_v32_dropdown():
    deepgram = {lang.code for lang in LANGUAGES if lang.deepgram}
    assert deepgram == _V32_DROPDOWN
    assert DEEPGRAM_BASE_LANGUAGES <= set(LANGUAGE_NAMES)


def test_whisper_entries_cover_openai_whisper_languages():
    whisper = {whisper_language_code(lang.code) for lang in LANGUAGES if lang.whisper}
    assert whisper - {"auto"} == _OPENAI_WHISPER_CODES


def test_regional_variants_and_multi_are_cloud_only():
    for lang in LANGUAGES:
        if "-" in lang.code or lang.code == "multi":
            assert lang.deepgram and not lang.whisper, lang.code
            assert lang.base in LANGUAGE_NAMES or lang.code == "multi"
    assert LANGUAGES_BY_CODE["auto"].whisper and LANGUAGES_BY_CODE["auto"].deepgram


def test_translation_targets_are_base_languages_without_english():
    assert TRANSLATION_CODES == set(LANGUAGE_NAMES) - {"en"}


def test_every_translation_target_is_taggable():
    from core.transcribe import NEUTRAL_SUBTITLE_LANG, resolve_subtitle_language_tag

    for code in TRANSLATION_CODES:
        assert resolve_subtitle_language_tag(requested_language=code) != NEUTRAL_SUBTITLE_LANG


def test_whisper_code_aliases_round_trip():
    assert whisper_language_code("jv") == "jw"
    assert whisper_language_code("pt-BR") == "pt"
    assert catalog_language_code("jw") == "jv"
    assert catalog_language_code("es") == "es"


def test_payload_puts_specials_first_then_sorted_by_name():
    payload = catalog_payload()
    assert [e["code"] for e in payload[:2]] == ["auto", "multi"]
    names = [e["name"].lower() for e in payload[2:]]
    assert names == sorted(names)
    assert set(payload[0]) == {
        "code",
        "name",
        "base",
        "deepgram",
        "whisper",
        "translate",
        "special",
    }
