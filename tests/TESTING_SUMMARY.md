# CLI Testing Suite - Summary

This testing suite provides comprehensive validation of all CLI functions for the Subgeneratorr.

## What Has Been Created

### 1. Test Plan Document
**File:** [`CLI_TEST_PLAN.md`](CLI_TEST_PLAN.md)

Comprehensive test plan covering:
- 12 test categories
- 40+ individual test cases
- Success criteria for each test
- Expected results and validation steps

### 2. Automated Test Script
**File:** [`test_cli_comprehensive.py`](test_cli_comprehensive.py)

Python script that automates testing with:
- 11 core test functions
- Colored terminal output
- Automatic result recording
- JSON report generation
- Setup validation
- Cleanup utilities

### 3. Test Files Requirements
**File:** [`TEST_FILES_REQUIREMENTS.md`](TEST_FILES_REQUIREMENTS.md)

Detailed specifications for:
- 5 required test files
- Format and duration requirements
- Content recommendations
- Cost estimates
- Quick creation commands

### 4. Testing Guide
**File:** [`README.md`](README.md)

Quick start guide with:
- Setup instructions
- Execution commands
- Troubleshooting tips
- Expected results

## Test Coverage

The test suite validates:

### ✅ Core Functions
- Audio extraction from video
- Deepgram API transcription
- SRT file generation
- Video duration detection
- Cost calculation

### ✅ File Management
- Directory scanning
- File extension filtering
- File list processing
- Skip logic for existing files
- Force regeneration

### ✅ Advanced Features
- Transcript generation with speaker diarization
- Speaker name mapping from CSV
- Keyterms auto-loading
- Multi-language support
- Batch size limiting

### ✅ Error Handling
- Silent video detection
- Invalid file handling
- API error management
- Graceful failure recovery

### ✅ Logging & Statistics
- JSON statistics generation
- Cost tracking
- Processing logs
- Debug output

## Quick Start Instructions

### Step 1: Prepare Test Files

You need to provide test media files. See [`TEST_FILES_REQUIREMENTS.md`](TEST_FILES_REQUIREMENTS.md) for complete specifications.

**Minimum requirement:** One video file with clear English speech (30-60 seconds)

**Recommended setup:**
```
test_data/
├── videos/
│   ├── short_test.mp4          # 30-60s English speech
│   ├── medium_test.mkv         # 2-3min, multiple speakers
│   ├── spanish_test.mp4        # 30-60s Spanish speech
│   └── silent_test.mp4         # 10-30s no speech
└── audio/
    └── test_audio.mp3          # 30-60s audio file
```

### Step 2: Run Tests

```bash
# From project root
cd /path/to/subgeneratorr

# Run the comprehensive test suite
python3 tests/test_cli_comprehensive.py

# Or specify custom test directory
python3 tests/test_cli_comprehensive.py /path/to/test_data
```

### Step 3: Review Results

Check the terminal output for:
- ✓ Passed tests (green)
- ✗ Failed tests (red)
- ⚠ Skipped tests (yellow)

Review the generated JSON report:
```bash
cat tests/test_report_*.json
```

## Test Execution Time & Cost

**Estimated duration:** 10-20 minutes (depending on video lengths)

**Estimated cost:** $0.05-$0.10 USD (Deepgram API)
- Short video (1 min): $0.0043
- Medium video (2.5 min): $0.0108
- Other tests: ~$0.02
- Multiple runs for regeneration tests

## What Gets Tested

### Test 1: Setup Check ✅
Validates environment configuration

### Test 2: Basic Video Transcription ✅
Tests the core workflow from video → SRT

### Test 3: Skip Existing SRT ✅
Verifies files with existing subtitles are skipped

### Test 4: Force Regenerate ✅
Tests regeneration of existing SRT files

### Test 5: Transcript Generation ✅
Tests speaker-labeled transcript creation

### Test 6: Speaker Map Application ✅
Tests character name mapping in transcripts

### Test 7: Keyterms Auto-load ✅
Tests automatic keyterm detection and loading

### Test 8: File List Processing ✅
Tests batch processing from text file

### Test 9: Batch Size Limiting ✅
Tests batch size restrictions

### Test 10: Silent Video Handling ✅
Tests error handling for no-speech videos

### Test 11: Statistics Generation ✅
Tests JSON log creation and accuracy

## Expected Success Rate

With proper test files:
- **Critical tests:** 100% pass (core transcription, SRT generation)
- **Important tests:** 90%+ pass (features, error handling)
- **Optional tests:** May be skipped if files not provided

## Next Steps

1. **Gather test files** - Follow [`TEST_FILES_REQUIREMENTS.md`](TEST_FILES_REQUIREMENTS.md)
2. **Place files** - Organize in `test_data/` directory structure
3. **Run tests** - Execute `python3 tests/test_cli_comprehensive.py`
4. **Review results** - Check terminal output and JSON report
5. **Iterate** - Fix any failures and re-run tests

## Files Created

```
tests/
├── CLI_TEST_PLAN.md                # Comprehensive test plan (567 lines)
├── TEST_FILES_REQUIREMENTS.md      # Test file specifications (401 lines)
├── test_cli_comprehensive.py       # Automated test script (889 lines)
├── README.md                       # Testing guide (209 lines)
├── TESTING_SUMMARY.md              # This file
└── test_report_*.json              # Generated after test run
```

## Benefits

✅ **Comprehensive Coverage** - Tests all CLI functions systematically
✅ **Automated Execution** - Runs all tests with one command
✅ **Clear Results** - Color-coded output and detailed reports
✅ **Cost Efficient** - Minimal API costs (~$0.10)
✅ **Easy Setup** - Clear requirements and instructions
✅ **Maintainable** - Well-documented and extensible

## Maintenance

To add new tests:
1. Add test case to `CLI_TEST_PLAN.md`
2. Implement test method in `test_cli_comprehensive.py`
3. Call test from `run_all_tests()` method
4. Update documentation

## Support & Troubleshooting

- Review [`README.md`](README.md) for troubleshooting tips
- Check [`TEST_FILES_REQUIREMENTS.md`](TEST_FILES_REQUIREMENTS.md) for file issues
- Verify Docker and API key setup
- Check `deepgram-logs/` for detailed processing logs

## Conclusion

This testing suite provides:
- **Complete validation** of all CLI functionality
- **Automated testing** with minimal manual intervention
- **Clear documentation** for setup and execution
- **Detailed reporting** of results

Once you provide the test files, simply run:
```bash
python3 tests/test_cli_comprehensive.py
```

And the suite will validate all CLI functions automatically!