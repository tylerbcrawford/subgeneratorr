#!/usr/bin/env python3
"""
Deepgram Transcript Generator with Speaker Diarization

Generates speaker-labeled transcripts from Deepgram API responses.
Supports speaker name mapping via CSV files.
"""

import csv
import json
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime


class TranscriptGenerator:
    """
    Handles generation of speaker-labeled transcripts.
    
    Processes Deepgram API responses with diarization enabled and creates
    human-readable transcripts with speaker labels. Supports mapping speaker
    IDs to character names via CSV files.
    """
    
    def __init__(self, speaker_map_path: Optional[str] = None):
        """
        Initialize the transcript generator.
        
        Args:
            speaker_map_path: Optional path to speaker mapping CSV file
        """
        self.speaker_map = self._load_speaker_map(speaker_map_path) if speaker_map_path else {}
    
    def _load_speaker_map(self, csv_path: str) -> Dict[int, str]:
        """
        Load speaker ID to name mappings from CSV file.
        
        CSV Format:
            speaker_id,name
            0,Walter
            1,Jesse
        
        Args:
            csv_path: Path to CSV file with speaker mappings
            
        Returns:
            Dictionary mapping speaker IDs to names
        """
        speaker_map = {}
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    speaker_id = int(row['speaker_id'])
                    speaker_map[speaker_id] = row['name']
            return speaker_map
        except FileNotFoundError:
            print(f"⚠️  Speaker map not found: {csv_path}")
            return {}
        except Exception as e:
            print(f"⚠️  Error loading speaker map: {e}")
            return {}
    
    def _get_speaker_label(self, speaker_id: int) -> str:
        """
        Get speaker label, using mapped name if available.
        
        Args:
            speaker_id: Numeric speaker ID from Deepgram
            
        Returns:
            Speaker name or "Speaker X" if no mapping exists
        """
        if speaker_id in self.speaker_map:
            return self.speaker_map[speaker_id]
        return f"Speaker {speaker_id}"
    
    def _format_timestamp(self, seconds: float) -> str:
        """
        Format seconds as HH:MM:SS.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted timestamp string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def generate_transcript(self, deepgram_response: dict, output_path: str) -> bool:
        """
        Generate speaker-labeled transcript from Deepgram response.
        
        Args:
            deepgram_response: Deepgram API response with diarization
            output_path: Path to save transcript file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Parse response
            results = deepgram_response.results if hasattr(deepgram_response, 'results') else deepgram_response.get('results')
            if not results:
                raise ValueError("No results in Deepgram response")
            
            channels = results.channels if hasattr(results, 'channels') else results.get('channels')
            if not channels or len(channels) == 0:
                raise ValueError("No channels in Deepgram response")
            
            channel = channels[0]
            alternatives = channel.alternatives if hasattr(channel, 'alternatives') else channel.get('alternatives')
            if not alternatives or len(alternatives) == 0:
                raise ValueError("No alternatives in channel")
            
            alternative = alternatives[0]
            
            # Get words with speaker information
            words = alternative.words if hasattr(alternative, 'words') else alternative.get('words')
            if not words or len(words) == 0:
                raise ValueError("No words detected in audio")
            
            # Group words by speaker and generate transcript
            transcript_lines = []
            current_speaker = None
            current_text = []
            current_start_time = None
            
            for word_obj in words:
                word = word_obj.word if hasattr(word_obj, 'word') else word_obj.get('word')
                start = word_obj.start if hasattr(word_obj, 'start') else word_obj.get('start')
                speaker = word_obj.speaker if hasattr(word_obj, 'speaker') else word_obj.get('speaker')
                
                # If speaker is None, use speaker 0 as default
                if speaker is None:
                    speaker = 0
                
                # New speaker detected
                if speaker != current_speaker:
                    # Save previous speaker's text
                    if current_speaker is not None and current_text:
                        speaker_label = self._get_speaker_label(current_speaker)
                        timestamp = self._format_timestamp(current_start_time)
                        text = ' '.join(current_text)
                        transcript_lines.append(f"[{timestamp}] {speaker_label}: {text}")
                    
                    # Start new speaker section
                    current_speaker = speaker
                    current_text = [word]
                    current_start_time = start
                else:
                    # Continue current speaker
                    current_text.append(word)
            
            # Add final speaker's text
            if current_text:
                speaker_label = self._get_speaker_label(current_speaker)
                timestamp = self._format_timestamp(current_start_time)
                text = ' '.join(current_text)
                transcript_lines.append(f"[{timestamp}] {speaker_label}: {text}")
            
            # Write transcript to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("# Speaker-Labeled Transcript\n")
                f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                if self.speaker_map:
                    f.write(f"# Speaker mappings applied: {len(self.speaker_map)} speakers\n")
                f.write("\n")
                for line in transcript_lines:
                    f.write(line + "\n")
            
            return True
            
        except Exception as e:
            print(f"❌ Transcript generation error: {e}")
            return False
    
    def save_debug_json(self, deepgram_response: dict, output_path: str):
        """
        Save raw Deepgram response for debugging.
        
        Args:
            deepgram_response: Deepgram API response
            output_path: Path to save JSON file
        """
        try:
            response_data = deepgram_response.to_dict() if hasattr(deepgram_response, 'to_dict') else deepgram_response
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(response_data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Debug JSON save failed: {e}")


def find_speaker_map(video_path: Path, speaker_maps_base: str) -> Optional[str]:
    """
    Find speaker map CSV file for a video based on its location.
    
    Searches for speaker_maps/ShowName/speakers.csv
    where ShowName is extracted from the video path.
    
    Args:
        video_path: Path to the video file
        speaker_maps_base: Base directory for speaker maps
        
    Returns:
        Path to speaker map CSV if found, None otherwise
    """
    try:
        # Extract show/movie name from path
        # Assumes structure: /media/tv/ShowName/Season X/episode.mkv
        # or: /media/movies/MovieName/movie.mkv
        parts = video_path.parts
        
        # Try to find show/movie name (usually 2-3 levels up from file)
        if len(parts) >= 3:
            # Try parent of parent (TV show case)
            show_name = parts[-3]
        elif len(parts) >= 2:
            # Try parent (movie case)
            show_name = parts[-2]
        else:
            return None
        
        # Build speaker map path
        speaker_map_dir = Path(speaker_maps_base) / show_name
        speaker_map_file = speaker_map_dir / "speakers.csv"
        
        if speaker_map_file.exists():
            return str(speaker_map_file)
        
        return None
        
    except Exception as e:
        print(f"⚠️  Error finding speaker map: {e}")
        return None