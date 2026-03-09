#!/usr/bin/env python3
"""
Post-process subtitle files to rename them with proper language tags.

This script renames subtitle files to use ISO-639-2 language codes (.eng.srt)
to ensure proper recognition by Plex and other media servers.

Transformations:
- *.srt → *.eng.srt (if no other language subtitles exist)
- *.en.srt → *.eng.srt

Usage:
    python postprocess_subtitles.py /path/to/file1.srt /path/to/file2.en.srt
    python postprocess_subtitles.py /media/library  # Process entire directory recursively
"""

import sys
from pathlib import Path
from typing import List


def relabel_to_eng(path: Path, dry_run: bool = False) -> bool:
    """
    Rename a subtitle file to use .eng.srt extension.
    
    Args:
        path: Path to subtitle file
        dry_run: If True, only show what would be renamed without actually renaming
        
    Returns:
        True if file was renamed (or would be renamed in dry-run), False otherwise
    """
    if not path.exists():
        print(f"⚠️  File not found: {path}")
        return False
    
    if not path.is_file():
        print(f"⚠️  Not a file: {path}")
        return False
    
    # Skip if already .eng.srt
    if path.name.endswith(".eng.srt"):
        print(f"✓  Already tagged: {path.name}")
        return False
    
    # Handle .en.srt → .eng.srt
    if path.name.endswith(".en.srt"):
        new_name = path.name[:-7] + ".eng.srt"  # Remove .en.srt, add .eng.srt
        new_path = path.parent / new_name
        
        if dry_run:
            print(f"Would rename: {path.name} → {new_name}")
        else:
            path.rename(new_path)
            print(f"✓  Renamed: {path.name} → {new_name}")
        return True
    
    # Handle bare .srt → .eng.srt
    if path.suffix == ".srt":
        # Check if other language subtitles exist
        stem = path.stem
        parent = path.parent
        
        # Look for other language tags (e.g., .fr.srt, .es.srt)
        other_langs = list(parent.glob(f"{stem}.*.srt"))
        other_langs = [f for f in other_langs if f != path and not f.name.endswith(".eng.srt")]
        
        if other_langs:
            print(f"⚠️  Skipping {path.name}: Other language subtitles exist")
            print(f"    Found: {', '.join(f.name for f in other_langs)}")
            return False
        
        new_name = stem + ".eng.srt"
        new_path = parent / new_name
        
        if dry_run:
            print(f"Would rename: {path.name} → {new_name}")
        else:
            path.rename(new_path)
            print(f"✓  Renamed: {path.name} → {new_name}")
        return True
    
    return False


def process_directory(directory: Path, dry_run: bool = False) -> dict:
    """
    Recursively process all subtitle files in a directory.
    
    Args:
        directory: Directory to process
        dry_run: If True, only show what would be renamed
        
    Returns:
        Dictionary with statistics (renamed, skipped, errors)
    """
    stats = {"renamed": 0, "skipped": 0, "errors": 0}
    
    print(f"\n🔍 Scanning directory: {directory}")
    print(f"{'=' * 70}\n")
    
    # Find all .srt files recursively
    srt_files = list(directory.rglob("*.srt"))
    
    if not srt_files:
        print("No .srt files found.")
        return stats
    
    print(f"Found {len(srt_files)} subtitle files\n")
    
    for srt_file in srt_files:
        try:
            if relabel_to_eng(srt_file, dry_run):
                stats["renamed"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            print(f"❌ Error processing {srt_file.name}: {e}")
            stats["errors"] += 1
    
    return stats


def print_summary(stats: dict, dry_run: bool = False):
    """Print summary statistics."""
    print(f"\n{'=' * 70}")
    print("📊 SUMMARY")
    print(f"{'=' * 70}")
    
    if dry_run:
        print(f"Would rename:  {stats['renamed']} files")
    else:
        print(f"✓  Renamed:    {stats['renamed']} files")
    
    print(f"⏭️  Skipped:    {stats['skipped']} files")
    
    if stats['errors'] > 0:
        print(f"❌ Errors:     {stats['errors']} files")
    
    print(f"{'=' * 70}")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: No files or directories specified")
        sys.exit(1)
    
    # Check for dry-run flag
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("🔍 DRY RUN MODE - No files will be modified\n")
        sys.argv.remove("--dry-run")
    
    stats = {"renamed": 0, "skipped": 0, "errors": 0}
    
    for arg in sys.argv[1:]:
        path = Path(arg)
        
        if not path.exists():
            print(f"❌ Path not found: {arg}")
            stats["errors"] += 1
            continue
        
        if path.is_file():
            try:
                if relabel_to_eng(path, dry_run):
                    stats["renamed"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                print(f"❌ Error processing {path.name}: {e}")
                stats["errors"] += 1
        
        elif path.is_dir():
            dir_stats = process_directory(path, dry_run)
            stats["renamed"] += dir_stats["renamed"]
            stats["skipped"] += dir_stats["skipped"]
            stats["errors"] += dir_stats["errors"]
        
        else:
            print(f"⚠️  Unknown path type: {arg}")
            stats["errors"] += 1
    
    print_summary(stats, dry_run)
    
    if dry_run:
        print("\nTo actually rename files, run without --dry-run flag")


if __name__ == "__main__":
    main()