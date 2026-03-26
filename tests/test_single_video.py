#!/usr/bin/env python3
"""
Test script to process a single media file.

Usage:
    python test_single_video.py /path/to/video.mp4
    
    Or modify the VIDEO_PATH variable below and run:
    python test_single_video.py
"""

import sys
from pathlib import Path

# Add CLI directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'cli'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from core.transcribe import resolve_subtitle_path
from generate_subtitles import SubtitleGenerator

# Default media path - update this to test with your file
VIDEO_PATH = "/media/tv/YourShow/Season 01/Episode01.mkv"

def main():
    # Use command line argument if provided, otherwise use default
    if len(sys.argv) > 1:
        video_path = Path(sys.argv[1])
    else:
        video_path = Path(VIDEO_PATH)
        print(f"Using default path. To specify a video, run:")
        print(f"  python test_single_video.py /path/to/your/video.mp4")
        print()
    
    print(f"Testing with: {video_path.name}")
    print(f"Full path: {video_path}")
    print()
    
    if not video_path.exists():
        print(f"❌ Error: Media file not found!")
        print(f"Please provide a valid media file path.")
        sys.exit(1)
    
    srt_path = resolve_subtitle_path(
        video_path,
        Config.LANGUAGE,
        detect_language=Config.DETECT_LANGUAGE,
    )
    if srt_path.exists():
        print(f"⚠️  Warning: SRT file already exists at {srt_path}")
        print(f"Delete it first to regenerate, or test with a different video.")
        sys.exit(0)
    
    print("Initializing Subgeneratorr...")
    gen = SubtitleGenerator()
    print()
    
    print("Processing video...")
    success = gen.process_video(video_path)
    
    if success:
        print()
        print("="*70)
        print("✅ TEST SUCCESSFUL")
        print("="*70)
        print(f"Generated subtitle file: {srt_path}")
        print()
        gen.print_summary()
        gen.save_stats()
    else:
        print()
        print("="*70)
        print("❌ TEST FAILED")
        print("="*70)
        sys.exit(1)

if __name__ == "__main__":
    main()
