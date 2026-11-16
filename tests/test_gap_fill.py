from pathlib import Path
from types import SimpleNamespace as NS

import srt as srt_lib

from core import gap_fill


def _w(word, start, end, p=0.9):
    return NS(word=" " + word, start=start, end=end, probability=p)


def _seg(words, text=None, nsp=0.1, lp=-0.3, cr=1.4):
    return NS(
        words=words,
        text=text or " ".join(w.word.strip() for w in words),
        no_speech_prob=nsp,
        avg_logprob=lp,
        compression_ratio=cr,
    )


class FakeModel:
    def __init__(self, segs):
        self.segs = segs

    def transcribe(self, buf, **kw):
        assert kw["vad_filter"] is False
        return iter(self.segs), None


def _resp(times):
    words = [NS(start=a, end=b) for a, b in times]
    return NS(results=NS(channels=[NS(alternatives=[NS(words=words)])]))


def test_find_gaps_head_middle_tail_and_threshold():
    times = [(12, 13), (14, 15), (25, 26)]
    assert gap_fill.find_gaps(times, 40, 10) == [(0.0, 12), (15, 25), (26, 40)]
    assert gap_fill.find_gaps(times, 35.9, 10) == [(0.0, 12), (15, 25)]
    assert gap_fill.find_gaps([], 30, 10) == [(0.0, 30)]


def test_should_gap_fill_gates(monkeypatch):
    base = dict(
        engine="deepgram",
        language="en",
        detect_language=False,
        profanity_filter="off",
        redact=None,
        multichannel=False,
    )
    monkeypatch.setattr(gap_fill, "whisper_available", lambda: True)
    monkeypatch.delenv("GAP_FILL", raising=False)
    assert gap_fill.should_gap_fill(**base) == (False, "disabled")
    monkeypatch.setenv("GAP_FILL", "on")
    assert gap_fill.should_gap_fill(**base)[0]
    for k, v in (
        ("engine", "whisper"),
        ("detect_language", True),
        ("language", "multi"),
        ("profanity_filter", "strict"),
        ("redact", ["pii"]),
        ("multichannel", True),
    ):
        assert not gap_fill.should_gap_fill(**{**base, k: v})[0], k
    monkeypatch.setattr(gap_fill, "whisper_available", lambda: False)
    assert not gap_fill.should_gap_fill(**base)[0]


def test_segment_filters_drop_hallucinations():
    good = _seg([_w("Get", 0, 0.3), _w("the", 0.3, 0.5), _w("car!", 0.5, 0.9)])
    assert gap_fill._segment_ok(good)
    assert not gap_fill._segment_ok(_seg([_w("Thank", 0, 1), _w("you.", 1, 2)], text=" Thank you."))
    assert not gap_fill._segment_ok(_seg(good.words, nsp=0.9, lp=-1.2))
    assert not gap_fill._segment_ok(_seg(good.words, cr=3.0))
    assert not gap_fill._segment_ok(_seg([_w("uh", 0, 1, p=0.05)]))
    assert not gap_fill._segment_ok(_seg([]))


def test_transcribe_gap_offsets_and_trims_to_bounds():
    segs = [_seg([_w("early", 0.0, 0.1), _w("Stop!", 1.0, 1.5), _w("late", 9.9, 10.0)])]
    out = gap_fill.transcribe_gap(FakeModel(segs), b"", 100.0, 100.2, 109.8, "en")
    assert [w.word for w in out[0].words] == ["Stop!"]
    assert out[0].words[0].start == 101.0


def _setup(tmp_path, monkeypatch, segs):
    srt_path = tmp_path / "x.en.srt"
    srt_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello.\n\n2\n00:00:30,000 --> 00:00:31,000\nBye.\n\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gap_fill, "_probe_duration", lambda p: 32.0)
    monkeypatch.setattr(gap_fill, "_slice", lambda *a: b"")
    monkeypatch.setattr(gap_fill, "speech_seconds", lambda buf: 5.0)
    monkeypatch.setattr(gap_fill.WhisperEngine, "_load_model", lambda self: FakeModel(segs))
    return srt_path, _resp([(1, 2), (30, 31)])


def test_gap_fill_merges_in_order_and_renumbers(tmp_path, monkeypatch):
    # gap is 2..30; fake model returns words relative to the slice start (2.0)
    segs = [_seg([_w("Get", 8.0, 8.3), _w("the", 8.3, 8.5), _w("car!", 8.5, 8.9)])]
    srt_path, resp = _setup(tmp_path, monkeypatch, segs)
    added = gap_fill.gap_fill_srt(srt_path, Path("a.flac"), resp, "en", replace=["car:truck"])
    cues = list(srt_lib.parse(srt_path.read_text()))
    assert added == 1
    assert [c.content for c in cues] == ["Hello.", "Get the truck!", "Bye."]
    assert [c.index for c in cues] == [1, 2, 3]
    assert cues[1].start.total_seconds() == 10.0
    assert cues[1].end <= cues[2].start


def test_gap_fill_no_speech_leaves_file_untouched(tmp_path, monkeypatch):
    srt_path, resp = _setup(tmp_path, monkeypatch, [])
    before = srt_path.read_bytes()
    assert gap_fill.gap_fill_srt(srt_path, Path("a.flac"), resp, "en") == 0
    assert srt_path.read_bytes() == before


def test_gap_fill_engine_failure_keeps_deepgram_srt(tmp_path, monkeypatch):
    srt_path, resp = _setup(tmp_path, monkeypatch, [])

    def boom(self):
        raise RuntimeError("no model")

    monkeypatch.setattr(gap_fill.WhisperEngine, "_load_model", boom)
    before = srt_path.read_bytes()
    assert gap_fill.gap_fill_srt(srt_path, Path("a.flac"), resp, "en") == 0
    assert srt_path.read_bytes() == before


def test_gap_fill_skips_blanks_without_speech(tmp_path, monkeypatch):
    segs = [_seg([_w("Get", 8.0, 8.3), _w("the", 8.3, 8.5), _w("car!", 8.5, 8.9)])]
    srt_path, resp = _setup(tmp_path, monkeypatch, segs)
    monkeypatch.setattr(gap_fill, "speech_seconds", lambda buf: 0.5)
    before = srt_path.read_bytes()
    assert gap_fill.gap_fill_srt(srt_path, Path("a.flac"), resp, "en") == 0
    assert srt_path.read_bytes() == before


def test_gap_fill_stops_when_budget_spent(tmp_path, monkeypatch):
    srt_path, resp = _setup(tmp_path, monkeypatch, [])
    monkeypatch.setattr(gap_fill, "GAP_FILL_BUDGET_SECONDS", 0)
    seen = []
    monkeypatch.setattr(gap_fill, "speech_seconds", lambda buf: seen.append(1) or 5.0)
    clock = iter([0.0, 10.0, 20.0, 30.0])
    monkeypatch.setattr(gap_fill.time, "monotonic", lambda: next(clock))
    assert gap_fill.gap_fill_srt(srt_path, Path("a.flac"), resp, "en") == 0
    assert seen == []
