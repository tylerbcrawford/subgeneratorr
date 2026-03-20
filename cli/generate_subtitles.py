#!/usr/bin/env python3
"""
Subgeneratorr CLI

Automatically generate SRT subtitle files for video content using Deepgram's AI-powered
speech-to-text API. Extracts audio from videos, transcribes with Deepgram, and creates
properly formatted SRT subtitle files.

Environment Variables:
    DEEPGRAM_API_KEY: Required - Your Deepgram API key
    MEDIA_PATH: Path to scan for videos (default: /media)
    FILE_LIST_PATH: Optional path to text file with video paths to process
    BATCH_SIZE: Max videos per run, 0=unlimited (default: 0)
    LANGUAGE: Language code for transcription (default: en)
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from deepgram import DeepgramClient, PrerecordedOptions
from deepgram_captions import DeepgramConverter, srt

from config import Config
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.transcribe import (
    get_transcripts_folder, get_json_folder, write_raw_json,
    load_keyterms_from_csv, save_keyterms_to_csv, find_speaker_map,
    extract_audio as core_extract_audio
)


class SubtitleGenerator:
    """
    Main subtitle generation class.
    
    Handles the complete workflow: finding videos, extracting audio,
    transcribing with Deepgram API, and generating SRT files.
    Tracks statistics and costs for each batch run.
    """
    
    def __init__(self):
        Config.validate()
        self.client = DeepgramClient(api_key=Config.DEEPGRAM_API_KEY)
        self.stats = {
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "total_minutes": 0,
            "failed_files": [],
            "start_time": datetime.now().isoformat()
        }
    
    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}", flush=True)
    
    def extract_audio(self, video_path: str) -> Optional[Path]:
        """
        Extract audio from video file using the core extract_audio function.

        Args:
            video_path: Path to source video file

        Returns:
            Path to extracted audio file, or None if extraction failed
        """
        try:
            return core_extract_audio(Path(video_path), language=Config.LANGUAGE)
        except Exception as e:
            self.log(f"  ❌ Audio extraction error: {str(e)[:200]}")
            return None
    
    def get_video_duration(self, video_path: str) -> float:
        """
        Get video duration in minutes using FFprobe.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Duration in minutes, or 0 if unable to determine
        """
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip()) / 60
        except Exception:
            return 0
    
    def transcribe_audio(self, audio_path: str, enable_diarization: bool = False, keyterms: list = None,
                        numerals: bool = False, filler_words: bool = False,
                        detect_language: bool = False, measurements: bool = False) -> Optional[dict]:
        """
        Transcribe audio file using Deepgram API.
        
        Args:
            audio_path: Path to audio file to transcribe
            enable_diarization: Enable speaker diarization for transcripts
            keyterms: Optional list of keyterms for better recognition (Nova-3)
            numerals: Convert spoken numbers to digits (e.g., "twenty twenty four" → "2024")
            filler_words: Include filler words like "uh", "um" in transcription (default: False)
            detect_language: Auto-detect language for international content
            measurements: Convert spoken measurements (e.g., "fifty meters" → "50m")
            
        Returns:
            Deepgram response object, or None if transcription failed
        """
        try:
            with open(audio_path, "rb") as f:
                buffer_data = f.read()
            
            # Convert profanity_filter to boolean for API compatibility
            use_profanity_filter = Config.PROFANITY_FILTER != "off"
            
            options = PrerecordedOptions(
                model=Config.MODEL,
                smart_format=True,
                utterances=True,
                punctuate=True,
                paragraphs=True,
                diarize=enable_diarization,
                language=Config.LANGUAGE,
                profanity_filter=use_profanity_filter
            )
            
            # Add keyterms if provided (Nova-3 feature)
            if keyterms and Config.MODEL == "nova-3":
                options.keyterm = keyterms
            
            # Add Nova-3 quality enhancement parameters
            if numerals:
                options.numerals = True
            
            if filler_words:
                options.filler_words = True
            
            if detect_language:
                options.detect_language = True
            
            if measurements:
                options.measurements = True
            
            response = self.client.listen.rest.v("1").transcribe_file(
                {"buffer": buffer_data}, options
            )
            return response
        except Exception as e:
            self.log(f"  ❌ Deepgram API error: {e}")
            return None
    
    def generate_srt(self, deepgram_response: dict) -> str:
        try:
            if Config.SAVE_RAW_JSON:
                debug_file = f"{Config.LOG_PATH}/deepgram_response_debug.json"
                try:
                    response_data = deepgram_response.to_dict() if hasattr(deepgram_response, 'to_dict') else str(deepgram_response)
                    with open(debug_file, 'w') as f:
                        json.dump(response_data, f, indent=2)
                    self.log(f"  🐛 Debug: Response saved to {debug_file}")
                except Exception as e:
                    self.log(f"  ⚠️  Debug save failed: {e}")
            
            # Check if we have valid results
            if not deepgram_response:
                raise ValueError("Empty Deepgram response")
            
            # Try to access results
            results = deepgram_response.results if hasattr(deepgram_response, 'results') else deepgram_response.get('results')
            if not results:
                raise ValueError("No results in Deepgram response")
            
            # Try to access channels
            channels = results.channels if hasattr(results, 'channels') else results.get('channels')
            if not channels or len(channels) == 0:
                raise ValueError("No channels in Deepgram response")
            
            channel = channels[0]
            
            # Try to access alternatives
            alternatives = channel.alternatives if hasattr(channel, 'alternatives') else channel.get('alternatives')
            if not alternatives or len(alternatives) == 0:
                raise ValueError("No alternatives in channel")
            
            alternative = alternatives[0]
            
            # Check for words
            words = alternative.words if hasattr(alternative, 'words') else alternative.get('words')
            if not words or len(words) == 0:
                raise ValueError("No words detected in audio - possibly silent video or no speech")
            
            self.log(f"  🎤 Detected {len(words)} words in transcription")
            
            transcription = DeepgramConverter(deepgram_response)
            return srt(transcription)
        except ValueError as e:
            raise Exception(f"SRT generation failed: {str(e)}")
        except Exception as e:
            raise Exception(f"SRT generation error: {str(e)}")
    
    def process_video(self, video_path: Path) -> bool:
        srt_path = video_path.with_suffix('.eng.srt')
        audio_path: Optional[Path] = None
        
        # Determine transcript path based on Transcripts folder structure
        if Config.ENABLE_TRANSCRIPT:
            transcripts_folder = get_transcripts_folder(video_path)
            transcript_path = transcripts_folder / f"{video_path.stem}.transcript.speakers.txt"
        else:
            transcript_path = video_path.with_suffix('.transcript.speakers.txt')
        
        synced_marker_path = video_path.with_suffix('.eng.synced')
        
        # Skip logic depends on whether transcript generation is enabled and force regenerate flag
        if not Config.FORCE_REGENERATE:
            if Config.ENABLE_TRANSCRIPT:
                # When transcript mode is enabled, skip only if BOTH exist
                if srt_path.exists() and transcript_path.exists():
                    self.log(f"⏭️  Skipping: {video_path.name} (SRT and transcript exist)")
                    self.stats["skipped"] += 1
                    return False
            else:
                # When transcript mode is disabled, skip if SRT exists
                if srt_path.exists():
                    self.log(f"⏭️  Skipping: {video_path.name} (SRT exists)")
                    self.stats["skipped"] += 1
                    return False
        else:
            # Force regenerate mode - always process
            if srt_path.exists() or transcript_path.exists():
                self.log(f"🔄 Force regenerating: {video_path.name}")
        
        self.log(f"🎬 Processing: {video_path.name}")
        
        # Auto-load keyterms from CSV if available
        keyterms = load_keyterms_from_csv(video_path)
        if keyterms:
            self.log(f"  📋 Auto-loaded {len(keyterms)} keyterms from CSV")
        
        try:
            duration = self.get_video_duration(str(video_path))
            cost = duration * Config.COST_PER_MINUTE
            self.log(f"  ⏱️  Duration: {duration:.1f} min | Cost: ${cost:.2f}")
            
            self.log("  📢 Extracting audio...")
            audio_path = self.extract_audio(str(video_path))
            if not audio_path:
                raise Exception("Audio extraction failed")
            
            # Track if SRT already existed
            srt_already_existed = srt_path.exists()
            
            # Generate SRT if it doesn't exist OR if force regenerate is enabled
            if not srt_already_existed or Config.FORCE_REGENERATE:
                self.log(f"  🧠 Transcribing (nova-3)...")
                response = self.transcribe_audio(
                    str(audio_path),
                    keyterms=keyterms,
                    numerals=Config.NUMERALS,
                    filler_words=Config.FILLER_WORDS,
                    detect_language=Config.DETECT_LANGUAGE,
                    measurements=Config.MEASUREMENTS
                )
                if not response:
                    raise Exception("Transcription failed")
                
                self.log("  💾 Generating SRT...")
                srt_content = self.generate_srt(response)
                
                with open(srt_path, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
                
                # Remove Subsyncarr marker file if it exists so Subsyncarr knows to reprocess
                if synced_marker_path.exists():
                    synced_marker_path.unlink()
                    self.log(f"  🗑️  Removed Subsyncarr marker: {synced_marker_path.name}")
                
                self.log(f"  ✅ SRT {'regenerated' if srt_already_existed else 'created'}: {srt_path.name}")
                self.stats["processed"] += 1
                self.stats["total_minutes"] += duration
            else:
                self.log(f"  ⏭️  SRT exists: {srt_path.name}")
            
            # Generate transcript if enabled
            if Config.ENABLE_TRANSCRIPT:
                self.log("  🗣️  Transcript feature enabled — generating diarized transcript...")
                transcript_generated = self._generate_transcript(
                    video_path,
                    audio_path,
                    response if not srt_already_existed or Config.FORCE_REGENERATE else None,
                    keyterms=keyterms
                )
                # Count as processed if we generated a transcript for an existing SRT
                if transcript_generated and srt_already_existed:
                    self.stats["processed"] += 1
                    self.stats["total_minutes"] += duration
            
            return True
            
        except Exception as e:
            self.log(f"  ❌ Error: {str(e)}")
            self.stats["failed"] += 1
            self.stats["failed_files"].append(str(video_path))
            return False
        finally:
            if audio_path and audio_path.exists():
                audio_path.unlink()
    
    def _generate_transcript(
        self,
        video_path: Path,
        audio_path: Path,
        existing_response: dict = None,
        keyterms: list = None,
    ) -> bool:
        """
        Generate speaker-labeled transcript for a video.
        
        Args:
            video_path: Path to the video file
            audio_path: Path to extracted audio file
            existing_response: Optional existing Deepgram response (reuse if provided)
            keyterms: Optional keyterms for transcription
            
        Returns:
            True if transcript was successfully generated, False otherwise
        """
        try:
            # Get Transcripts folder
            transcripts_folder = get_transcripts_folder(video_path)
            transcript_path = transcripts_folder / f"{video_path.stem}.transcript.speakers.txt"
            
            # Auto-detect speaker map from Transcripts/Speakermap/
            speaker_map_path = find_speaker_map(video_path)
            if speaker_map_path:
                self.log(f"  📋 Using speaker map: {speaker_map_path}")
            else:
                self.log(f"  📋 No speaker map found, using generic labels")
            
            # Use existing response or transcribe with diarization enabled
            if existing_response:
                self.log(f"  🎤 Using existing transcription response for transcript...")
                response = existing_response
            else:
                self.log(f"  🎤 Transcribing with speaker diarization...")
                response = self.transcribe_audio(
                    str(audio_path),
                    enable_diarization=True,
                    keyterms=keyterms,
                    numerals=Config.NUMERALS,
                    filler_words=Config.FILLER_WORDS,
                    detect_language=Config.DETECT_LANGUAGE,
                    measurements=Config.MEASUREMENTS
                )
                if not response:
                    self.log(f"  ⚠️  Transcript transcription failed")
                    return False
            
            # Generate transcript using new write_transcript from core
            from core.transcribe import write_transcript
            write_transcript(response, transcript_path, speaker_map_path)
            self.log(f"  ✅ Transcript created: {transcript_path}")
            
            # Save raw JSON if enabled
            if Config.SAVE_RAW_JSON:
                try:
                    write_raw_json(response, video_path)
                    json_folder = get_json_folder(video_path)
                    self.log(f"  🐛 Raw JSON saved to: {json_folder}")
                except Exception as e:
                    self.log(f"  ⚠️  Raw JSON save failed: {e}")
            
            return True
            
        except Exception as e:
            self.log(f"  ⚠️  Transcript error (SRT unaffected): {e}")
            return False
    
    def read_video_list_from_file(self, file_path: str) -> List[Path]:
        """Read video file paths from a text file (one path per line)"""
        self.log(f"📄 Reading file list from: {file_path}")
        video_paths = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Convert to Path object
                    video_path = Path(line)
                    
                    # Check if file exists
                    if not video_path.exists():
                        self.log(f"  ⚠️  Line {line_num}: File not found: {line}")
                        continue
                    
                    # Check if it's a video file
                    if video_path.suffix.lower() not in Config.VIDEO_EXTENSIONS:
                        self.log(f"  ⚠️  Line {line_num}: Not a video file: {line}")
                        continue
                    
                    # Check if files already exist based on mode (unless force regenerate is enabled)
                    srt_path = video_path.with_suffix('.eng.srt')
                    
                    # Check for transcript in Transcripts folder if transcript mode is enabled
                    if Config.ENABLE_TRANSCRIPT:
                        transcripts_folder = get_transcripts_folder(video_path)
                        transcript_path = transcripts_folder / f"{video_path.stem}.transcript.speakers.txt"
                    else:
                        transcript_path = video_path.with_suffix('.transcript.speakers.txt')
                    
                    if not Config.FORCE_REGENERATE:
                        if Config.ENABLE_TRANSCRIPT:
                            # When transcript mode is enabled, skip only if BOTH exist
                            if srt_path.exists() and transcript_path.exists():
                                self.log(f"  ⏭️  Line {line_num}: SRT and transcript exist, skipping: {video_path.name}")
                                self.stats["skipped"] += 1
                                continue
                        else:
                            # When transcript mode is disabled, skip if SRT exists
                            if srt_path.exists():
                                self.log(f"  ⏭️  Line {line_num}: SRT exists, skipping: {video_path.name}")
                                self.stats["skipped"] += 1
                                continue
                    
                    video_paths.append(video_path)
            
            self.log(f"📊 Found {len(video_paths)} videos to process from file list")
            return video_paths
            
        except FileNotFoundError:
            self.log(f"❌ File list not found: {file_path}")
            return []
        except Exception as e:
            self.log(f"❌ Error reading file list: {e}")
            return []
    
    def find_videos_without_subtitles(self) -> List[Path]:
        self.log(f"🔍 Scanning {Config.MEDIA_PATH}...")
        videos_needing_processing = []
        
        for root, dirs, files in os.walk(Config.MEDIA_PATH):
            for file in files:
                if Path(file).suffix.lower() in Config.VIDEO_EXTENSIONS:
                    video_path = Path(root) / file
                    srt_path = video_path.with_suffix('.eng.srt')
                    
                    # Check for transcript in Transcripts folder if transcript mode is enabled
                    if Config.ENABLE_TRANSCRIPT:
                        transcripts_folder = get_transcripts_folder(video_path)
                        transcript_path = transcripts_folder / f"{video_path.stem}.transcript.speakers.txt"
                    else:
                        transcript_path = video_path.with_suffix('.transcript.speakers.txt')
                    
                    if Config.FORCE_REGENERATE:
                        # Force regenerate mode - include all videos
                        videos_needing_processing.append(video_path)
                    elif Config.ENABLE_TRANSCRIPT:
                        # When transcript mode is enabled, find videos missing either file
                        if not srt_path.exists() or not transcript_path.exists():
                            videos_needing_processing.append(video_path)
                    else:
                        # When transcript mode is disabled, find videos without SRT
                        if not srt_path.exists():
                            videos_needing_processing.append(video_path)
        
        if Config.FORCE_REGENERATE:
            self.log(f"📊 Found {len(videos_needing_processing)} videos to force regenerate")
        elif Config.ENABLE_TRANSCRIPT:
            self.log(f"📊 Found {len(videos_needing_processing)} videos needing processing")
        else:
            self.log(f"📊 Found {len(videos_needing_processing)} videos without subtitles")
        return videos_needing_processing
    
    def save_stats(self):
        self.stats["end_time"] = datetime.now().isoformat()
        self.stats["estimated_cost"] = self.stats["total_minutes"] * Config.COST_PER_MINUTE
        self.stats["model"] = Config.MODEL
        self.stats["language"] = Config.LANGUAGE
        
        os.makedirs(Config.LOG_PATH, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = Path(Config.LOG_PATH) / f"deepgram_stats_{timestamp}.json"
        
        with open(log_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
        
        self.log(f"📈 Stats saved: {log_file}")
    
    def print_summary(self):
        self.log("\n" + "="*70)
        self.log("✨ BATCH COMPLETE")
        self.log("="*70)
        self.log(f"✅ Processed:      {self.stats['processed']} files")
        self.log(f"⏭️  Skipped:        {self.stats['skipped']} files")
        self.log(f"❌ Failed:         {self.stats['failed']} files")
        self.log(f"⏱️  Total Duration: {self.stats['total_minutes']:.1f} minutes")
        
        cost = self.stats['total_minutes'] * Config.COST_PER_MINUTE
        self.log(f"💰 Estimated Cost: ${cost:.2f}")
        self.log("="*70)
        
        if self.stats["failed_files"]:
            self.log("\n⚠️  Failed Files:")
            for failed_file in self.stats["failed_files"]:
                self.log(f"  - {failed_file}")
    
    def run(self):
        self.log("🚀 Starting Subgeneratorr")
        self.log(f"🤖 Model: {Config.MODEL}")
        self.log(f"🌍 Language: {Config.LANGUAGE}")
        if Config.FORCE_REGENERATE:
            self.log(f"🔄 Force Regenerate: ENABLED (will regenerate existing SRT files)")
        
        # Check if we're using a file list or directory scanning
        if Config.FILE_LIST_PATH:
            self.log(f"📄 Mode: File List")
            self.log(f"📄 File List: {Config.FILE_LIST_PATH}")
            videos = self.read_video_list_from_file(Config.FILE_LIST_PATH)
        else:
            self.log(f"📁 Mode: Directory Scan")
            self.log(f"📁 Media Path: {Config.MEDIA_PATH}")
            videos = self.find_videos_without_subtitles()
        
        if not Config.FILE_LIST_PATH and Config.BATCH_SIZE == 0:
            Config.BATCH_SIZE = 10
            self.log(f"⚠️  No BATCH_SIZE set for directory scan — defaulting to {Config.BATCH_SIZE}")
        
        if Config.BATCH_SIZE > 0:
            self.log(f"🎯 Batch Size: {Config.BATCH_SIZE} videos")
        else:
            self.log(f"🎯 Batch Size: Unlimited")
        
        if not videos:
            self.log("✨ No videos need subtitles!")
            return
        
        if Config.BATCH_SIZE > 0:
            videos = videos[:Config.BATCH_SIZE]
            self.log(f"🎯 Processing {len(videos)} videos in this batch")
        
        total = len(videos)
        for idx, video_path in enumerate(videos, 1):
            self.log(f"\n{'─'*70}")
            self.log(f"📹 Video {idx}/{total}")
            self.process_video(video_path)
            
            if idx % 5 == 0:
                cost_so_far = self.stats['total_minutes'] * Config.COST_PER_MINUTE
                self.log(f"\n🔄 Checkpoint: {idx}/{total} | Cost: ${cost_so_far:.2f}")
        
        self.print_summary()
        self.save_stats()


def main():
    try:
        generator = SubtitleGenerator()
        generator.run()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
