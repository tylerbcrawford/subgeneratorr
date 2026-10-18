#!/usr/bin/env python3
"""
KeytermSearcher._parse_response against real model replies: hedged answers
with a disclaimer and a second list, labelled groups, preambles, and clean
comma-separated lists that must pass through unchanged.
"""

from core.keyterm_search import KeytermSearcher

# Claude Sonnet 5.5, Tears of Steel (2012): list, disclaimer, revised list
SONNET_HEDGED = """Thom,Celia,Barty,Ellie,Rob,Sintel,Captain Tamara,Dr. Dr. Vidal,Vidal,Amsterdam,Oude Kerk,Oude Kerk church,Nieuwe Kerk,Tears of Steel,Blender Foundation,Blender,Neural,Rhapsody,Moonbase,Kleiner,Sofia,Dr. Slenderman,gate,Gate 7,Ibis,Rho,sonic,sonic dagger,Lunar Gate,Ibis Rho,Rhapsody Bot,Robo,Metal Hydra,Nanobot,Emmi,Thorn,Sentinel,Corpus,Corpus Christi

I should be upfront: I couldn't verify the cast and dialogue details for this short film (it's a 2012 Blender Foundation open-movie project with sparse documentation), so some entries above are low-confidence guesses. A more reliable, verified list covering what I'm confident appears in the film:

Thom,Celia,Barty,Rob,Ellie,Captain Tamara,Amsterdam,Oude Kerk,Tears of Steel,Blender Foundation,Blender,robot,robots,bot,Sintel,warrior
"""

# Claude Haiku 5.5, same title: preamble paragraph, then labelled groups
HAIKU_LABELLED = """Tears of Steel (2012) is a short film by Blender Foundation with a sci-fi setting. Its dialogue is sparse and I can't browse, so the list below draws on what I know of its characters and world; please verify spellings against the film's credits or subtitle file before use.

Characters: Thom,Celia,Sergio,Vanja,Hitch,Morgan,Gaia

Places and terms: Amsterdam,Mad Oak,Blender,Tears of Steel,Mad Oak Studio,RoboCop,Watchdog,robot,cyborg,mechanical,Dutch,Mad Oak Hotel
"""

# GPT-6 Luna: clean list with spaces after commas
LUNA_CLEAN = (
    "Thom, Barley, Celia, Galle, Bjorn, Shandor, Cobalt, Amsterdam, Rotterdam, "
    "Mr. Barley, Captain, cyborg, bio-engineered cells, artificial intelligence"
)


def parse(text):
    searcher = KeytermSearcher.__new__(KeytermSearcher)
    return searcher._parse_response(text)


def _no_prose(terms):
    for term in terms:
        assert len(term.split()) <= 6, term
        assert "\n" not in term


def test_hedged_reply_keeps_only_the_revised_list():
    terms = parse(SONNET_HEDGED)
    assert terms == [
        "Thom",
        "Celia",
        "Barty",
        "Rob",
        "Ellie",
        "Captain Tamara",
        "Amsterdam",
        "Oude Kerk",
        "Tears of Steel",
        "Blender Foundation",
        "Blender",
        "robot",
        "robots",
        "bot",
        "Sintel",
        "warrior",
    ]


def test_lines_never_fuse_into_one_term():
    terms = parse("Corpus,Corpus Christi\nThom,Celia")
    assert terms == ["Corpus", "Corpus Christi", "Thom", "Celia"]


def test_labelled_groups_are_merged_and_labels_stripped():
    terms = parse(HAIKU_LABELLED)
    assert terms[:7] == ["Thom", "Celia", "Sergio", "Vanja", "Hitch", "Morgan", "Gaia"]
    assert terms[-1] == "Mad Oak Hotel"
    assert len(terms) == 19
    assert not any(":" in t for t in terms)
    _no_prose(terms)


def test_bold_and_bulleted_labels():
    text = "**Characters:** Thom, Celia\n- **Places:** Amsterdam, Oude Kerk"
    assert parse(text) == ["Thom", "Celia", "Amsterdam", "Oude Kerk"]


def test_label_only_lines_are_dropped():
    text = "Characters:\nThom, Celia\n\n**Places**:\nAmsterdam"
    assert parse(text) == ["Thom", "Celia", "Amsterdam"]


def test_prose_fragments_with_commas_do_not_leak():
    text = (
        "Thom,Celia,robot\n"
        "I trimmed duplicates and anything about bot memory, so here is a cleaned, final list:\n"
        "Thom,Celia,robot,Memory Lane"
    )
    terms = parse(text)
    assert terms == ["Thom", "Celia", "robot", "Memory Lane"]


def test_trailing_note_is_dropped():
    text = "Thom, Celia, Amsterdam\n\nPlease verify spellings against the credits before use."
    assert parse(text) == ["Thom", "Celia", "Amsterdam"]


def test_one_term_per_line_list():
    text = "Here are the keyterms:\n- Thom\n- Celia\n- Captain Tamara\n1. Oude Kerk"
    assert parse(text) == ["Thom", "Celia", "Captain Tamara", "Oude Kerk"]


def test_fenced_list_is_unwrapped_not_discarded():
    assert parse("```\nThom,Celia\n```") == ["Thom", "Celia"]


def test_clean_lists_pass_through_unchanged():
    assert parse("Thom,Celia,Barley,robot hand") == ["Thom", "Celia", "Barley", "robot hand"]
    assert parse(LUNA_CLEAN) == [t.strip() for t in LUNA_CLEAN.split(",")]


def test_catchphrases_and_abbreviations_survive():
    text = "Walter White,Better call Saul,Yeah, science!,Mr. Charles,dream within a dream"
    assert parse(text) == [
        "Walter White",
        "Better call Saul",
        "Yeah",
        "science!",
        "Mr. Charles",
        "dream within a dream",
    ]


def test_dedupes_case_insensitively_and_strips_quotes():
    assert parse('"Thom", thom, `Celia`, **Celia**') == ["Thom", "Celia"]


def test_every_provider_gets_the_no_caveats_system_prompt(monkeypatch):
    from types import SimpleNamespace

    import core.keyterm_search as keyterm_search
    from core.llm_providers import LLMModel, LLMProvider

    seen = {}

    def fake_call_llm(provider, model, api_key, prompt, **kw):
        seen.update(kw)
        return SONNET_HEDGED, 1293, 424

    monkeypatch.setattr(keyterm_search, "call_llm", fake_call_llm)
    searcher = KeytermSearcher(LLMProvider.ANTHROPIC, LLMModel.CLAUDE_SONNET_5_5, "k")
    monkeypatch.setattr(searcher, "_build_prompt", lambda *a, **k: "prompt")
    result = searcher.generate_from_metadata(SimpleNamespace(media_type="movie"))
    assert seen["system_prompt"] == keyterm_search.KEYTERM_SYSTEM_PROMPT
    assert "caveats" in seen["system_prompt"]
    assert result["keyterms"][-1] == "warrior"
