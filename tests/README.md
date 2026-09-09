# Tests

## Unit suite (run this)

```bash
make test          # or: pytest tests/ -v
```

164 tests covering the ASR engine interface and capability gating, the SRT writer, subtitle detection and skip logic, language tagging, speaker labels, LLM provider adapters, translation, and the Web API (browse, capabilities, library scan, submit, translate). No Docker, media files, or API keys required — external calls are stubbed. CI runs the same command on every push, and the release workflow gates image publishing on it.

## Integration tests (optional, needs Docker + a Deepgram key)

`test_cli_comprehensive.py` drives the real CLI container against sample media and is not part of `make test`. Its test plan and the media files it expects are documented in [`docs/testing/`](../docs/testing/):

- [`cli-test-plan.md`](../docs/testing/cli-test-plan.md) — test cases and success criteria
- [`test-files-requirements.md`](../docs/testing/test-files-requirements.md) — how to lay out `test_data/`

```bash
python3 tests/test_cli_comprehensive.py [path/to/test_data]
```

`test_single_video.py` is the quick single-file smoke test for the same setup.
