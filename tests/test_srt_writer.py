"""Tests for the native SRT writer (core/srt_writer.py) — cue segmentation policy."""

import pytest
import srt as srt_lib

from core.asr_engine import NormalizedResult, NormalizedSegment, NormalizedWord
from core.srt_writer import (
    MAX_CUE_SECONDS,
    MAX_LINE_CHARS,
    MAX_LINES,
    build_srt,
    write_normalized_srt,
)


def _words(spec):
    """spec: list of (word, start, end)"""
    return [NormalizedWord(word=w, start=s, end=e) for w, s, e in spec]


def _seg(start, end, text, words=None):
    return NormalizedSegment(start=start, end=end, text=text, words=words or [])


# ---------------------------------------------------------------------------
# Golden file: exact byte output for a fixed fixture
# ---------------------------------------------------------------------------

GOLDEN_RESULT = NormalizedResult(
    segments=[
        _seg(
            0.0,
            2.0,
            "Hello there.",
            _words([("Hello", 0.0, 1.0), ("there.", 1.2, 2.0)]),
        ),
        _seg(
            3.0,
            8.4,
            "One two three four five six seven eight",
            _words(
                [
                    ("One", 3.0, 3.4),
                    ("two", 3.5, 3.9),
                    ("three", 4.0, 4.4),
                    ("four", 4.5, 4.9),
                    ("five", 5.0, 5.4),
                    ("six", 5.5, 5.9),
                    # 1.6s gap — must split here
                    ("seven", 7.5, 7.9),
                    ("eight", 8.0, 8.4),
                ]
            ),
        ),
        _seg(
            10.0,
            14.4,
            "This is a considerably longer sentence that needs wrapping.",
            _words(
                [
                    ("This", 10.0, 10.4),
                    ("is", 10.5, 10.9),
                    ("a", 11.0, 11.4),
                    ("considerably", 11.5, 11.9),
                    ("longer", 12.0, 12.4),
                    ("sentence", 12.5, 12.9),
                    ("that", 13.0, 13.4),
                    ("needs", 13.5, 13.9),
                    ("wrapping.", 14.0, 14.4),
                ]
            ),
        ),
    ],
    detected_language="en",
)

GOLDEN_SRT = """\
1
00:00:00,000 --> 00:00:02,000
Hello there.

2
00:00:03,000 --> 00:00:05,900
One two three four five six

3
00:00:07,500 --> 00:00:08,500
seven eight

4
00:00:10,000 --> 00:00:14,400
This is a considerably longer sentence
that needs wrapping.

"""


def test_golden_file_exact_output():
    assert build_srt(GOLDEN_RESULT) == GOLDEN_SRT


# ---------------------------------------------------------------------------
# Policy: line length + line count
# ---------------------------------------------------------------------------


def _cues(text):
    return list(srt_lib.parse(text))


def test_no_line_exceeds_max_chars_and_two_lines():
    words = []
    t = 0.0
    for i in range(30):
        words.append((f"word{i:02d}", t, t + 0.25))
        t += 0.3
    result = NormalizedResult(
        segments=[_seg(0.0, t, " ".join(w for w, _, _ in words), _words(words))]
    )
    for cue in _cues(build_srt(result)):
        lines = cue.content.split("\n")
        assert len(lines) <= MAX_LINES
        for line in lines:
            assert len(line) <= MAX_LINE_CHARS


def test_overlong_single_word_is_not_broken():
    long_word = "Donaudampfschifffahrtsgesellschaftskapitän!"  # > 42 chars
    result = NormalizedResult(
        segments=[_seg(0.0, 2.0, long_word, _words([(long_word, 0.0, 2.0)]))]
    )
    cues = _cues(build_srt(result))
    assert cues[0].content == long_word


# ---------------------------------------------------------------------------
# Policy: max duration + gap splitting
# ---------------------------------------------------------------------------


def test_long_segment_splits_on_duration():
    words = []
    for i in range(20):
        start = i * 0.5
        words.append((f"w{i:02d}", start, start + 0.4))
    result = NormalizedResult(
        segments=[_seg(0.0, 9.9, " ".join(w for w, _, _ in words), _words(words))]
    )
    cues = _cues(build_srt(result))
    assert len(cues) == 2
    for cue in cues:
        assert (cue.end - cue.start).total_seconds() <= MAX_CUE_SECONDS


def test_gap_splits_cue():
    result = NormalizedResult(
        segments=[
            _seg(
                0.0,
                5.0,
                "before after",
                _words([("before", 0.0, 1.0), ("after", 4.0, 5.0)]),
            )
        ]
    )
    cues = _cues(build_srt(result))
    assert len(cues) == 2
    assert cues[0].content == "before"
    assert cues[1].content == "after"


def test_sentence_punctuation_splits_cue():
    result = NormalizedResult(
        segments=[
            _seg(
                0.0,
                4.0,
                "First sentence. Second one",
                _words(
                    [
                        ("First", 0.0, 0.5),
                        ("sentence.", 0.6, 1.0),
                        ("Second", 1.2, 1.7),
                        ("one", 1.8, 4.0),
                    ]
                ),
            )
        ]
    )
    cues = _cues(build_srt(result))
    assert len(cues) == 2
    assert cues[0].content == "First sentence."


# ---------------------------------------------------------------------------
# Policy: minimum duration
# ---------------------------------------------------------------------------


def test_short_cue_extended_to_min_duration():
    result = NormalizedResult(
        segments=[_seg(0.0, 0.3, "Hi.", _words([("Hi.", 0.0, 0.3)]))]
    )
    cues = _cues(build_srt(result))
    assert (cues[0].end - cues[0].start).total_seconds() == pytest.approx(1.0)


def test_min_duration_extension_bounded_by_next_cue():
    result = NormalizedResult(
        segments=[
            _seg(0.0, 0.3, "Hi.", _words([("Hi.", 0.0, 0.3)])),
            _seg(0.5, 2.0, "Bye now.", _words([("Bye", 0.5, 1.0), ("now.", 1.1, 2.0)])),
        ]
    )
    cues = _cues(build_srt(result))
    assert cues[0].end <= cues[1].start


# ---------------------------------------------------------------------------
# Fallback: segments without word timestamps
# ---------------------------------------------------------------------------


def test_wordless_segment_single_chunk():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    result = NormalizedResult(segments=[_seg(0.0, 6.0, text)])
    cues = _cues(build_srt(result))
    assert len(cues) == 1
    assert cues[0].start.total_seconds() == 0.0
    assert cues[0].end.total_seconds() == pytest.approx(6.0)
    assert cues[0].content.replace("\n", " ") == text


def test_wordless_segment_splits_proportionally():
    text = (
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
        "nu xi omicron pi rho sigma tau upsilon phi chi psi omega"
    )
    result = NormalizedResult(segments=[_seg(0.0, 12.0, text)])
    cues = _cues(build_srt(result))
    assert len(cues) >= 2
    reconstructed = " ".join(c.content.replace("\n", " ") for c in cues)
    assert reconstructed == text
    for prev, nxt in zip(cues, cues[1:]):
        assert prev.end <= nxt.start
    assert cues[0].start.total_seconds() == 0.0
    assert cues[-1].end.total_seconds() == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# Contract: empty result + file writing
# ---------------------------------------------------------------------------


def test_empty_result_raises():
    with pytest.raises(ValueError, match="No speech detected"):
        build_srt(NormalizedResult(segments=[]))


def test_write_normalized_srt_lang_suffix(tmp_path):
    dest = tmp_path / "Movie.srt"
    out = write_normalized_srt(GOLDEN_RESULT, dest, lang="eng")
    assert out.name == "Movie.eng.srt"
    assert out.read_text(encoding="utf-8") == GOLDEN_SRT


def test_write_normalized_srt_respects_resolved_path(tmp_path):
    dest = tmp_path / "Movie.eng.srt"
    out = write_normalized_srt(GOLDEN_RESULT, dest, lang="eng")
    assert out == dest
    assert out.exists()
