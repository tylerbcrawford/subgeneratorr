#!/usr/bin/env python3
"""
Analyze transcription timing data from job logs.

This script reads the job logs and calculates statistics to improve
the processing time estimation algorithm.
"""

import json
import statistics
from pathlib import Path

LOG_ROOT = Path(__file__).parent.parent / "deepgram-logs"

def analyze_timing_data():
    """Analyze timing data from job logs."""
    
    # Collect timing data from job logs
    time_multipliers = []
    processing_times = []
    video_durations = []
    
    if not LOG_ROOT.exists():
        print("❌ Log directory not found. Make sure you've run some transcription jobs first.")
        return
    
    log_files = list(LOG_ROOT.glob("job_*.json"))
    
    if not log_files:
        print("❌ No job logs found. Run some transcription jobs first to collect data.")
        return
    
    print(f"📊 Found {len(log_files)} job logs. Analyzing...\n")
    
    successful_jobs = 0
    for log_file in log_files:
        try:
            with open(log_file, 'r') as f:
                data = json.load(f)
            
            # Only analyze successful jobs with timing data
            if data.get('status') == 'ok' and 'time_multiplier' in data:
                time_multipliers.append(data['time_multiplier'])
                processing_times.append(data['processing_time_seconds'])
                video_durations.append(data['video_duration_seconds'])
                successful_jobs += 1
                
        except Exception as e:
            print(f"⚠️  Warning: Could not parse {log_file.name}: {e}")
            continue
    
    if not time_multipliers:
        print("❌ No timing data found in logs. Make sure you're running the updated version.")
        return
    
    # Calculate statistics
    avg_multiplier = statistics.mean(time_multipliers)
    median_multiplier = statistics.median(time_multipliers)
    min_multiplier = min(time_multipliers)
    max_multiplier = max(time_multipliers)
    
    if len(time_multipliers) > 1:
        stdev_multiplier = statistics.stdev(time_multipliers)
    else:
        stdev_multiplier = 0
    
    total_video_duration = sum(video_durations)
    total_processing_time = sum(processing_times)
    
    # Print results
    print("=" * 70)
    print("TIMING ANALYSIS RESULTS")
    print("=" * 70)
    print(f"\n📈 Sample Size: {successful_jobs} transcription jobs")
    print(f"\n⏱️  Total Video Duration: {format_time(total_video_duration)}")
    print(f"⚙️  Total Processing Time: {format_time(total_processing_time)}")
    
    print(f"\n📊 TIME MULTIPLIER STATISTICS:")
    print(f"   Current estimate: 0.1x (10% of video length)")
    print(f"   Average:  {avg_multiplier:.4f}x ({avg_multiplier * 100:.2f}% of video length)")
    print(f"   Median:   {median_multiplier:.4f}x ({median_multiplier * 100:.2f}% of video length)")
    print(f"   Minimum:  {min_multiplier:.4f}x ({min_multiplier * 100:.2f}% of video length)")
    print(f"   Maximum:  {max_multiplier:.4f}x ({max_multiplier * 100:.2f}% of video length)")
    
    if len(time_multipliers) > 1:
        print(f"   Std Dev:  {stdev_multiplier:.4f}x")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    print(f"   Suggested multiplier: {avg_multiplier:.4f}x")
    print(f"   Conservative estimate: {avg_multiplier + stdev_multiplier:.4f}x (avg + 1 std dev)")
    
    # Show per-job breakdown if requested
    print(f"\n📋 INDIVIDUAL JOB BREAKDOWN:")
    print(f"{'Video Duration':<20} {'Processing Time':<20} {'Multiplier':<15}")
    print("-" * 70)
    
    for vd, pt, tm in sorted(zip(video_durations, processing_times, time_multipliers)):
        print(f"{format_time(vd):<20} {format_time(pt):<20} {tm:.4f}x")
    
    print("\n" + "=" * 70)
    print(f"\n✅ To update the estimate in web/app.py:")
    print(f"   Change PROCESSING_TIME_MULTIPLIER from 0.1 to {avg_multiplier:.4f}")
    print("=" * 70)

def format_time(seconds):
    """Format seconds as MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

if __name__ == "__main__":
    analyze_timing_data()