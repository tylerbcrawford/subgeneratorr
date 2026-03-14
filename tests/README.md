# CLI Testing Suite

This directory contains comprehensive tests for the Subgeneratorr CLI tool.

## Contents

- [`CLI_TEST_PLAN.md`](CLI_TEST_PLAN.md) - Detailed test plan with all test cases
- [`TEST_FILES_REQUIREMENTS.md`](TEST_FILES_REQUIREMENTS.md) - Specifications for required test files
- [`test_cli_comprehensive.py`](test_cli_comprehensive.py) - Automated test script
- [`test_single_video.py`](test_single_video.py) - Simple single video test

## Quick Start

### 1. Prepare Test Files

Follow the instructions in [`TEST_FILES_REQUIREMENTS.md`](TEST_FILES_REQUIREMENTS.md) to prepare your test media files.

**Minimum requirements:**
- One video file with clear English speech (30-60 seconds)
- Place in `test_data/videos/` directory

**Recommended:**
- Short video (30-60s)
- Medium video with 2+ speakers (2-3 minutes)
- Spanish/non-English video
- Silent video
- Audio file (MP3)

### 2. Run the Test Suite

```bash
# From project root directory
cd /path/to/subgeneratorr

# Make test script executable
chmod +x tests/test_cli_comprehensive.py

# Run all tests (default test_data directory)
python3 tests/test_cli_comprehensive.py

# Or specify custom test directory
python3 tests/test_cli_comprehensive.py /path/to/your/test_data
```

### 3. Review Results

The test script will:
- Display colored output showing pass/fail for each test
- Generate a summary report with statistics
- Save detailed JSON report to `tests/test_report_YYYYMMDD_HHMMSS.json`

## Test Categories

The comprehensive test suite covers:

1. **Core Transcription** - Basic video transcription, audio extraction, SRT generation
2. **File Discovery** - Directory scanning, file extension filtering, file list processing
3. **Skip Logic** - Existing file detection, force regeneration
4. **Transcript Generation** - Speaker diarization, speaker name mapping
5. **Keyterms** - Auto-loading from CSV files
6. **Languages** - Multi-language support
7. **Batch Processing** - Batch size limits
8. **Error Handling** - Silent videos, invalid files, API errors
9. **Statistics** - JSON log generation, cost tracking

## Expected Results

- **Total Tests:** ~11-15 depending on available test files
- **Duration:** 5-15 minutes depending on video lengths
- **Cost:** ~$0.05-$0.10 USD (Deepgram API charges)

## Test Output Example

```
╔═══════════════════════════════════════════════════════════════════╗
║   Subgeneratorr - Comprehensive CLI Test Suite     ║
╚═══════════════════════════════════════════════════════════════════╝

============================================================
TEST: Setup Check
============================================================

[12:34:56] ✓ Environment file (.env) found
[12:34:56] ✓ Docker Compose file found
[12:34:56] ✓ Test data directory found
[12:34:56] ✓ Found 4 test files
[12:34:56] ✓ Test passed: Setup Check

============================================================
TEST 1.1: Basic Video Transcription
============================================================

[12:35:00] ℹ Running: docker compose run --profile cli --rm -e MEDIA_PATH=/path/test_data/videos -e BATCH_SIZE=1 cli
[12:35:45] ✓ File exists: short_test.eng.srt
[12:35:45] ✓ All patterns found in short_test.eng.srt
[12:35:45] ✓ Processed: 1 files
[12:35:45] ✓ Cost: $0.0043
[12:35:45] ✓ Test passed: Basic Video Transcription

... (more tests)

============================================================
TEST REPORT
============================================================

Test Summary:
  Total Tests:   11
  Passed:        9
  Failed:        0
  Skipped:       2
  Duration:      245.3s
  Success Rate:  100.0%

Detailed Results:
  [PASSED] Setup Check
    └─ Environment validation
  [PASSED] Basic Video Transcription
    └─ SRT file created and formatted correctly
  [PASSED] Skip Existing SRT
    └─ Existing files skipped correctly
  ... (more results)

✓ Report saved to: tests/test_report_20260301_123456.json
```

## Individual Tests

You can also run individual tests by modifying the `test_cli_comprehensive.py` script:

```python
# Run only specific tests
runner = CLITestRunner("test_data")
runner.test_setup_check()
runner.test_basic_video_transcription()
runner.generate_report()
```

## Troubleshooting

### "No test videos found"
- Ensure test files are in `test_data/videos/` directory
- Check file extensions are supported (.mp4, .mkv, .avi, etc.)

### "Setup not complete"
- Verify `.env` file exists with valid `DEEPGRAM_API_KEY`
- Verify `docker-compose.yml` exists
- Run `docker compose build` to ensure image is built

### "Command failed" or "Docker error"
- Ensure Docker is running
- Check Docker Compose version: `docker compose version`
- Verify API key is valid: check Deepgram dashboard

### "Insufficient API credits"
- Check your Deepgram account balance
- Estimated cost: ~$0.05-$0.10 for full test suite

### Tests taking too long
- Reduce video file durations (aim for 30-60 seconds)
- Run fewer tests by commenting out test calls
- Use `BATCH_SIZE=1` to limit processing

## Cleanup

After testing, clean up generated files:

```bash
# Remove all generated SRT and transcript files
find test_data -name "*.eng.srt" -delete
find test_data -name "*.transcript.speakers.txt" -delete
find test_data -type d -name "Transcripts" -exec rm -rf {} +

# Or use the cleanup function in the test script
python3 -c "from tests.test_cli_comprehensive import CLITestRunner; CLITestRunner('test_data').cleanup_test_outputs()"
```

## Contributing

When adding new tests:
1. Add test case to `CLI_TEST_PLAN.md`
2. Implement test method in `test_cli_comprehensive.py`
3. Add test call to `run_all_tests()` method
4. Update this README with new test information

## Support

For issues or questions:
- Review the test plan: [`CLI_TEST_PLAN.md`](CLI_TEST_PLAN.md)
- Check file requirements: [`TEST_FILES_REQUIREMENTS.md`](TEST_FILES_REQUIREMENTS.md)
- Open an issue in the project repository