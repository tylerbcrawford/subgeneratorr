# CLI Test Plan for Subgeneratorr

**Version:** 1.0  
**Date:** 2025-10-21  
**Purpose:** Comprehensive testing of all CLI functions

---

## Test Environment Setup

### Required Test Files
1. **Short video** (~30-60 seconds) - For basic transcription tests
2. **Medium video** (~2-3 minutes) - For transcript and speaker diarization tests
3. **Multi-language video** - For language detection tests
4. **Audio file** (MP3/WAV) - For audio-only transcription tests
5. **Silent/No-speech video** - For error handling tests

### Test Directory Structure
```
test_data/
├── videos/
│   ├── short_test.mp4          # 30-60 seconds, clear speech
│   ├── medium_test.mkv         # 2-3 minutes, multiple speakers
│   ├── spanish_test.mp4        # Spanish language content
│   └── silent_test.mp4         # No audio or silent
├── audio/
│   └── test_audio.mp3          # Audio file for audio-only test
├── file_lists/
│   ├── test_list.txt           # File list for batch processing
│   └── empty_list.txt          # Empty file list
└── TestShow/
    └── Transcripts/             # Generated during tests
        ├── Keyterms/
        │   └── TestShow_keyterms.csv    # Test keyterms file
        └── Speakermap/
            └── speakers.csv     # Test speaker map
```

---

## Test Cases

### 1. Core Transcription Functions

#### Test 1.1: Basic Video Transcription
**Function:** `extract_audio()`, `transcribe_audio()`, `generate_srt()`  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e BATCH_SIZE=1 \
  cli
```
**Expected Results:**
- Audio extracted successfully
- Deepgram API called
- `short_test.eng.srt` created
- Cost logged correctly
- Processing statistics saved

#### Test 1.2: Audio-Only File Transcription
**Function:** `is_audio()`, `transcribe_file()`  
**Setup:** Place MP3 file in test directory
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/audio \
  cli
```
**Expected Results:**
- Audio file detected and processed
- No FFmpeg extraction needed
- SRT file created for audio

#### Test 1.3: Video Duration Detection
**Function:** `get_video_duration()`  
**Expected Results:**
- Accurate duration calculated
- Cost estimation correct
- Duration logged in statistics

---

### 2. File Discovery and Filtering

#### Test 2.1: Directory Scanning
**Function:** `find_videos_without_subtitles()`  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  cli
```
**Expected Results:**
- All video files discovered
- Existing SRT files detected
- Only files without SRT processed

#### Test 2.2: File Extension Filtering
**Function:** Video extension detection  
**Expected Results:**
- `.mkv`, `.mp4`, `.avi`, `.mov` detected
- Non-video files ignored
- Hidden files ignored

#### Test 2.3: File List Processing
**Function:** `read_video_list_from_file()`  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e FILE_LIST_PATH=/test_data/file_lists/test_list.txt \
  cli
```
**Expected Results:**
- All listed files processed
- Comments and empty lines ignored
- Invalid paths reported
- File existence validated

---

### 3. Skip Logic and Force Regeneration

#### Test 3.1: Skip Existing SRT
**Function:** Skip logic in `process_video()`  
**Setup:** Create existing SRT file
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  cli
```
**Expected Results:**
- Videos with existing SRT skipped
- Skip count incremented
- No API calls for skipped files

#### Test 3.2: Force Regeneration
**Function:** `FORCE_REGENERATE` flag  
**Setup:** Existing SRT files present
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e FORCE_REGENERATE=1 \
  cli
```
**Expected Results:**
- All files processed regardless of existing SRT
- Existing SRT files overwritten
- Subsyncarr marker removed
- Cost incurred for all files

---

### 4. Transcript Generation

#### Test 4.1: Basic Transcript Generation
**Function:** `_generate_transcript()`, `write_transcript()`  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e ENABLE_TRANSCRIPT=1 \
  cli
```
**Expected Results:**
- Transcripts folder created
- `.transcript.speakers.txt` generated
- Speaker diarization enabled
- Generic speaker labels used

#### Test 4.2: Transcript with Speaker Map
**Function:** `find_speaker_map()`, speaker mapping  
**Setup:** Create speaker map CSV
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e ENABLE_TRANSCRIPT=1 \
  cli
```
**Expected Results:**
- Speaker map auto-detected
- Character names used instead of "Speaker 0"
- Proper name mapping applied

#### Test 4.3: Transcript Folder Structure
**Function:** `get_transcripts_folder()`, `get_speakermap_folder()`  
**Expected Results:**
- Transcripts/ created at correct level
- Season detection working for TV shows
- Movie directory structure respected

---

### 5. Keyterms Feature

#### Test 5.1: Auto-load Keyterms from CSV
**Function:** `load_keyterms_from_csv()`  
**Setup:** Create keyterms CSV file
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  cli
```
**Expected Results:**
- Keyterms CSV auto-detected
- Keyterms loaded and logged
- Keyterms passed to API
- Improved accuracy for specified terms

#### Test 5.2: Keyterms with Nova-3
**Function:** Keyterm API parameter  
**Expected Results:**
- Keyterms accepted by API
- Model confirmed as nova-3
- No errors with keyterm parameter

---

### 6. Language Support

#### Test 6.1: English Transcription (Default)
**Function:** Default language parameter  
**Expected Results:**
- Language set to "en"
- English transcription accurate
- `.eng.srt` file created

#### Test 6.2: Spanish Transcription
**Function:** Language parameter override  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e LANGUAGE=es \
  cli
```
**Expected Results:**
- Language set to "es"
- Spanish transcription accurate
- `.spa.srt` file created (if implemented)

---

### 7. Batch Processing

#### Test 7.1: Batch Size Limit
**Function:** `BATCH_SIZE` parameter  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e BATCH_SIZE=2 \
  cli
```
**Expected Results:**
- Only 2 videos processed
- Remaining files left for next run
- Batch size logged

#### Test 7.2: Zero Batch Size Fallback
**Function:** `BATCH_SIZE=0`  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e BATCH_SIZE=0 \
  cli
```
**Expected Results:**
- Defaults to batch size of 10 when set to 0 (see CLI docs)

---

### 8. Error Handling

#### Test 8.1: Silent Video Handling
**Function:** Empty transcription detection  
**Setup:** Video with no speech
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  cli
```
**Expected Results:**
- Error caught gracefully
- Clear error message: "No words detected"
- Failed count incremented
- No SRT file created
- Other videos continue processing

#### Test 8.2: Invalid API Key
**Function:** API authentication  
**Setup:** Invalid API key in .env
**Expected Results:**
- Clear authentication error
- Process exits with error code
- No partial files created

#### Test 8.3: Missing File in List
**Function:** File validation in list  
**Setup:** Non-existent file in list
**Expected Results:**
- Warning logged for missing file
- File skipped
- Processing continues for valid files

#### Test 8.4: FFmpeg Extraction Failure
**Function:** `extract_audio()` error handling  
**Setup:** Corrupted video file
**Expected Results:**
- FFmpeg error caught
- Error logged
- File marked as failed
- Temp audio cleaned up

---

### 9. Logging and Statistics

#### Test 9.1: Statistics Generation
**Function:** `save_stats()`, `print_summary()`  
**Expected Results:**
- JSON file created in deepgram-logs/
- Processed count accurate
- Skipped count accurate
- Failed count accurate
- Total minutes calculated
- Estimated cost correct
- Model and language logged

#### Test 9.2: Debug JSON Output
**Function:** `write_raw_json()`, `SAVE_RAW_JSON`  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e SAVE_RAW_JSON=1 \
  -e ENABLE_TRANSCRIPT=1 \
  cli
```
**Expected Results:**
- Raw JSON saved to Transcripts/JSON/
- JSON contains full Deepgram response
- Proper indentation and formatting

#### Test 9.3: Log Messages
**Function:** `log()` method  
**Expected Results:**
- Timestamps on all messages
- Clear progress indicators
- Cost information displayed
- File names shown
- Speaker map detection logged

---

### 10. Configuration and Validation

#### Test 10.1: Config Validation
**Function:** `Config.validate()`  
**Setup:** Missing API key
**Expected Results:**
- Clear error message
- Process exits before processing
- No files created

#### Test 10.2: Model Configuration
**Function:** Model selection  
**Expected Results:**
- Nova-3 model used
- Cost per minute = $0.0057/min
- Model logged in statistics

#### Test 10.3: Profanity Filter
**Function:** Profanity filter parameter  
**Test A:** Default (off)
**Test B:** Environment variable set
**Expected Results:**
- Filter applied according to setting
- Boolean value sent to API

---

### 11. File Organization

#### Test 11.1: SRT File Naming
**Function:** Proper language tagging  
**Expected Results:**
- Files named `video.eng.srt`
- Language code matches setting
- Files placed next to source video

#### Test 11.2: Transcript Folder Structure
**Function:** Folder creation and organization  
**Expected Results:**
- Transcripts/ folder created
- JSON/ subfolder created (if enabled)
- Keyterms/ subfolder exists
- Speakermap/ subfolder exists

#### Test 11.3: Temp File Cleanup
**Function:** Temporary audio cleanup  
**Expected Results:**
- Temp audio removed after success
- Temp audio removed after failure
- No orphaned temp files

---

### 12. Integration Tests

#### Test 12.1: Full Workflow - Single Video
**Function:** Complete end-to-end  
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e BATCH_SIZE=1 \
  -e ENABLE_TRANSCRIPT=1 \
  -e SAVE_RAW_JSON=1 \
  cli
```
**Expected Results:**
- Audio extracted
- Transcription completed
- SRT file created
- Transcript created
- JSON saved
- Statistics logged
- All temp files cleaned

#### Test 12.2: Full Workflow - Batch with Speaker Maps
**Function:** Complete workflow with all features  
**Setup:** Multiple videos with speaker maps and keyterms
**Command:**
```bash
docker compose run --profile cli --rm \
  -e MEDIA_PATH=/test_data/videos \
  -e ENABLE_TRANSCRIPT=1 \
  cli
```
**Expected Results:**
- Multiple videos processed
- Speaker maps applied
- Keyterms auto-loaded
- All features working together

---

## Success Criteria

### Critical (Must Pass)
- [ ] Basic video transcription works
- [ ] SRT files properly formatted
- [ ] Cost calculation accurate
- [ ] Skip logic prevents reprocessing
- [ ] Error handling graceful

### Important (Should Pass)
- [ ] Transcript generation works
- [ ] Speaker maps detected and applied
- [ ] Keyterms auto-loaded
- [ ] File list processing works
- [ ] Batch limiting works
- [ ] Statistics accurately logged

### Nice to Have (Can Have Minor Issues)
- [ ] Multi-language support
- [ ] Debug JSON output
- [ ] Force regeneration
- [ ] Audio-only files

---

## Test Execution Order

1. **Setup Phase** - Prepare test files and directory structure
2. **Core Functions** - Test basic transcription (Tests 1.x)
3. **Discovery** - Test file finding (Tests 2.x)
4. **Skip Logic** - Test existing file handling (Tests 3.x)
5. **Features** - Test transcripts, keyterms, speaker maps (Tests 4.x, 5.x)
6. **Error Handling** - Test failure scenarios (Test 8.x)
7. **Integration** - Full workflow tests (Tests 12.x)
8. **Cleanup** - Remove test artifacts

---

## Test Execution Notes

- Run tests in isolated test directory
- Use small test files to minimize API costs
- Check API balance before running all tests
- Estimated total cost: ~$0.50-$1.00 for full test suite
- Estimated time: 30-45 minutes

---

## Recommended Test Audio Files

You can create your own or use public domain content:

1. **Short Test (30-60s):** Public domain speech from LibriVox or similar
2. **Medium Test (2-3min):** Dialogue from public domain films
3. **Spanish Test:** Public domain Spanish content
4. **Silent Test:** Create with FFmpeg: `ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 10 -q:a 9 -acodec libmp3lame silent.mp3`

---

## Post-Test Validation

After running tests, verify:
- [ ] All SRT files properly formatted
- [ ] Transcripts readable and accurate
- [ ] No temp files left behind
- [ ] Logs contain expected information
- [ ] Cost calculations match actual API usage
- [ ] Docker containers clean up properly
