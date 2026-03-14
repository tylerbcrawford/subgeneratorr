# Test Files Requirements for CLI Testing

This document specifies the test files needed to run the comprehensive CLI test suite.

---

## Directory Structure

Please organize test files in the following structure:

```
test_data/
├── videos/
│   ├── short_test.mp4          # File 1: Short video
│   ├── medium_test.mkv         # File 2: Medium video
│   ├── spanish_test.mp4        # File 3: Spanish language
│   └── silent_test.mp4         # File 4: Silent video
├── audio/
│   └── test_audio.mp3          # File 5: Audio file
├── file_lists/
│   └── test_list.txt           # Created automatically by test script
└── TestShow/
    └── Transcripts/
        └── Speakermap/
            └── speakers.csv     # Optional: For speaker map testing
```

---

## Required Test Files

### File 1: Short Video (short_test.mp4)

**Purpose:** Basic transcription testing, batch processing, skip logic

**Specifications:**
- **Duration:** 30-60 seconds
- **Format:** MP4, MKV, or AVI
- **Audio:** Clear English speech
- **Content:** Any content with spoken dialogue (e.g., news clip, interview, movie scene)
- **Quality:** Standard definition or higher
- **Audio track:** Mono or stereo, 16kHz+ sample rate

**Recommendations:**
- News broadcast clips work well
- Movie trailers with clear dialogue
- Public domain content from Archive.org
- TED talk excerpts
- Podcast clips

**Example sources:**
- YouTube clips (use youtube-dl/yt-dlp to download)
- Public domain films from Archive.org
- Creative Commons content

---

### File 2: Medium Video (medium_test.mkv)

**Purpose:** Transcript generation, speaker diarization, longer processing tests

**Specifications:**
- **Duration:** 2-3 minutes
- **Format:** MKV, MP4, or AVI
- **Audio:** Clear English speech with **multiple speakers** (2-3 people)
- **Content:** Dialogue between multiple people (interview, conversation, debate)
- **Quality:** Standard definition or higher
- **Audio track:** Mono or stereo, 16kHz+ sample rate

**Recommendations:**
- Interview clips with 2-3 people
- Podcast episodes with multiple hosts
- Movie/TV scenes with dialogue between characters
- Panel discussions
- News segments with anchor + guest

**Important:** Should have distinct speakers for diarization testing

**Example sources:**
- TV show clips with 2-3 characters talking
- Interview videos
- Podcast episodes with co-hosts

---

### File 3: Spanish Language Video (spanish_test.mp4)

**Purpose:** Multi-language support testing

**Specifications:**
- **Duration:** 30-60 seconds
- **Format:** MP4, MKV, or AVI
- **Audio:** Clear **Spanish** speech
- **Content:** Any Spanish dialogue
- **Quality:** Standard definition or higher
- **Audio track:** Mono or stereo, 16kHz+ sample rate

**Recommendations:**
- Spanish news clips
- Spanish movie/TV show clips
- Spanish YouTube content
- Spanish language tutorials

**Alternative languages:** If Spanish is difficult to find, you can substitute with:
- French (fr)
- German (de)
- Portuguese (pt)
- Italian (it)

Just note which language you use, and we'll adjust the test accordingly.

**Example sources:**
- Spanish news networks (CNN en Español, BBC Mundo)
- Spanish movies/TV shows
- Spanish YouTube creators

---

### File 4: Silent Video (silent_test.mp4)

**Purpose:** Error handling for videos without speech

**Specifications:**
- **Duration:** 10-30 seconds
- **Format:** MP4, MKV, or AVI
- **Audio:** One of the following:
  - No audio track at all
  - Audio track with only music/no speech
  - Audio track with silence
  - Audio track with ambient noise but no clear speech
- **Quality:** Any

**How to create (if needed):**

**Option A: Create with FFmpeg (silent video):**
```bash
# Create a 10-second silent video with black screen
ffmpeg -f lavfi -i color=black:s=640x480:d=10 \
       -f lavfi -i anullsrc=r=44100:cl=mono \
       -c:v libx264 -c:a aac -t 10 -y silent_test.mp4
```

**Option B: Create with FFmpeg (music only, no speech):**
```bash
# Take any video and replace audio with sine wave (simulates music without speech)
ffmpeg -i input.mp4 \
       -f lavfi -i "sine=frequency=440:duration=10" \
       -map 0:v -map 1:a -c:v copy -c:a aac \
       -shortest -y silent_test.mp4
```

**Option C: Use existing content:**
- Music video instrumental sections
- Nature documentary with only ambient sounds
- Time-lapse videos

---

### File 5: Audio File (test_audio.mp3)

**Purpose:** Audio-only transcription testing (no video)

**Specifications:**
- **Duration:** 30-60 seconds
- **Format:** MP3, WAV, FLAC, OGG, or M4A
- **Content:** Clear English speech
- **Quality:** 16kHz+ sample rate, 64kbps+ bitrate

**Recommendations:**
- Podcast clips
- Audiobook excerpts
- Radio broadcasts
- Voice memos
- Any audio recording with clear speech

**How to create (if needed):**
```bash
# Extract audio from any video file
ffmpeg -i input.mp4 -vn -acodec mp3 -ar 16000 -ac 1 test_audio.mp3
```

**Example sources:**
- Podcast episodes (download directly as MP3)
- Convert from YouTube audio
- Record your own voice memo

---

## Optional Files for Enhanced Testing

### Speaker Map CSV (optional but recommended)

**Location:** `test_data/videos/TestShow/Transcripts/Speakermap/speakers.csv`

**Purpose:** Test speaker name mapping functionality

**Format:**
```csv
speaker_id,name
0,Alice
1,Bob
2,Charlie
```

**Instructions:**
1. After running the medium video test with transcripts enabled
2. Open the generated `.transcript.speakers.txt` file
3. Note which speaker IDs appear (e.g., "Speaker 0", "Speaker 1")
4. Create the CSV file mapping those IDs to test names
5. Re-run the test to verify names are applied

---

### Keyterms CSV (optional but recommended)

**Location:** `test_data/videos/Transcripts/Keyterms/TestShow_keyterms.csv`

**Purpose:** Test keyterm auto-loading functionality

**Format:** One keyterm per line (no headers)
```csv
important term
product name
character name
technical jargon
```

**Example for a movie clip:**
```csv
Darth Vader
lightsaber
Force
Skywalker
Jedi
```

**Instructions:**
1. Create the Transcripts/Keyterms/ directory structure
2. Add keyterms relevant to your test video content
3. Name the file matching your video's show/movie name

---

## Quick Start Summary

**Minimum viable test set:**
1. One short video with clear English speech (30-60 seconds)
2. One medium video with 2+ speakers (2-3 minutes)

**Recommended complete set:**
1. Short English video (30-60 seconds)
2. Medium multi-speaker video (2-3 minutes)
3. Non-English video (30-60 seconds, any language)
4. Silent/no-speech video (10-30 seconds)
5. Audio-only file (30-60 seconds)

---

## Cost Estimate

Running the full test suite with recommended files:

| File | Duration | Cost (Nova-3) |
|------|----------|---------------|
| Short video | 1 min | $0.0043 |
| Medium video | 2.5 min | $0.0108 |
| Spanish video | 1 min | $0.0043 |
| Silent video | 0.5 min | $0.0022 |
| Audio file | 1 min | $0.0043 |
| **Total** | **6 min** | **~$0.026** |

**Note:** Some tests run multiple times (e.g., force regenerate), so actual cost may be $0.05-$0.10 for the full suite.

---

## Verification Checklist

Before running tests, verify you have:

- [ ] At least one video file in `test_data/videos/`
- [ ] Video file(s) have clear audio with speech
- [ ] Audio file in `test_data/audio/` (optional but recommended)
- [ ] At least one file with multiple speakers (for diarization test)
- [ ] Silent/no-speech file (for error handling test)
- [ ] Non-English file (for language test, optional)
- [ ] Docker and Docker Compose installed
- [ ] `.env` file with valid `DEEPGRAM_API_KEY`
- [ ] Sufficient API credits (~$0.10 minimum)

---

## File Naming Convention

You can name files differently if preferred, but the test script expects:
- Files to be in `test_data/videos/` or `test_data/audio/`
- Standard video extensions: `.mp4`, `.mkv`, `.avi`, `.mov`, `.m4v`, `.wmv`, `.flv`
- Standard audio extensions: `.mp3`, `.wav`, `.flac`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.wma`

The test script will automatically discover and process files based on extension.

---

## Troubleshooting

**Q: Where can I find public domain test content?**
- Archive.org (Internet Archive) - public domain films and audio
- YouTube Creative Commons content
- LibriVox (public domain audiobooks)
- Wikimedia Commons

**Q: Can I use copyrighted content for testing?**
- Yes, for personal testing purposes, but don't redistribute the test files
- Ensure you're only testing on your local system

**Q: What if I can't find a Spanish video?**
- Use any non-English language you have access to
- Or skip that specific test (mark it as optional)

**Q: Can I use the same file multiple times?**
- Yes! You can copy one file multiple times with different names
- The tests mainly care about file processing, not unique content

**Q: My video file is too long/short**
- Short durations: Anything 15+ seconds works
- Long durations: Cut with FFmpeg: `ffmpeg -i input.mp4 -t 60 -c copy output.mp4`

---

## Example: Quick Test File Creation

If you just want to test quickly with minimal setup:

```bash
# 1. Create test directory structure
mkdir -p test_data/videos test_data/audio

# 2. Download a short YouTube clip (requires yt-dlp)
yt-dlp -f 'bv*[height<=480]+ba' --output test_data/videos/short_test.mp4 \
  "https://www.youtube.com/watch?v=VIDEO_ID"

# 3. Extract audio from the video
ffmpeg -i test_data/videos/short_test.mp4 -vn -acodec mp3 \
  test_data/audio/test_audio.mp3

# 4. Create a silent test file
ffmpeg -f lavfi -i color=black:s=640x480:d=10 \
       -f lavfi -i anullsrc=r=44100:cl=mono \
       -c:v libx264 -c:a aac -t 10 -y test_data/videos/silent_test.mp4

# 5. Copy the video for medium test
cp test_data/videos/short_test.mp4 test_data/videos/medium_test.mkv

# Done! You now have a minimal test set
```

---

## Need Help?

If you have trouble finding or creating test files, you can:
1. Use sample files from the project's examples directory (if available)
2. Record your own voice with a phone/computer
3. Use screen recordings with audio
4. Download Creative Commons content from YouTube

The key requirement is: **clear English speech** in at least one video file.