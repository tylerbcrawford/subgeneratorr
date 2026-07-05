#!/usr/bin/env python3
"""
Tests for stripping deepgram-captions "[speaker N]" lines from SRT output
(core/transcribe.py strip_speaker_labels). Subtitles are label-free by
default; the tags are opt-in via speaker_labels / SPEAKER_LABELS.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_core_dependency_stubs():
    if "deepgram" not in sys.modules:
        deepgram = types.ModuleType("deepgram")
        deepgram.DeepgramClient = type("DeepgramClient", (), {})
        deepgram.PrerecordedOptions = type("PrerecordedOptions", (), {})
        sys.modules["deepgram"] = deepgram
    if "deepgram_captions" not in sys.modules:
        deepgram_captions = types.ModuleType("deepgram_captions")
        deepgram_captions.DeepgramConverter = object
        deepgram_captions.srt = object()
        sys.modules["deepgram_captions"] = deepgram_captions


_install_core_dependency_stubs()

from core.transcribe import strip_speaker_labels  # noqa: E402

LABELED = """\
1
00:00:01,000 --> 00:00:02,000
[speaker 0]
Good afternoon, Greendale.

2
00:00:02,500 --> 00:00:03,500
I am your dean.

3
00:00:04,000 --> 00:00:05,000
[speaker 1]
"""


def test_strips_label_lines_but_keeps_dialogue():
    result = strip_speaker_labels(LABELED)
    assert "[speaker" not in result
    assert "Good afternoon, Greendale." in result
    assert "I am your dean." in result


def test_drops_label_only_cues_and_renumbers():
    result = strip_speaker_labels(LABELED)
    blocks = [b for b in result.strip().split("\n\n") if b]
    assert len(blocks) == 2
    assert blocks[0].startswith("1\n")
    assert blocks[1].startswith("2\n")


def test_unlabeled_srt_passes_through():
    plain = "1\n00:00:01,000 --> 00:00:02,000\nHello there.\n"
    result = strip_speaker_labels(plain)
    assert "Hello there." in result
    assert len([b for b in result.strip().split("\n\n") if b]) == 1


def test_case_insensitive_and_multiline_cues():
    text = "1\n00:00:01,000 --> 00:00:02,000\n[Speaker 12]\nline one\nline two\n"
    result = strip_speaker_labels(text)
    assert "[Speaker" not in result
    assert "line one\nline two" in result


def test_speaker_mention_inside_dialogue_is_kept():
    """Only whole-line label markers are stripped, not dialogue about speakers."""
    text = "1\n00:00:01,000 --> 00:00:02,000\nThe [speaker 0] tag is metadata.\n"
    result = strip_speaker_labels(text)
    assert "The [speaker 0] tag is metadata." in result
