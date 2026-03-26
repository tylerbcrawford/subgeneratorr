#!/usr/bin/env python3
"""
Comprehensive CLI Test Script for Subgeneratorr

This script tests all major functions of the CLI tool including:
- Basic transcription
- File discovery and filtering
- Skip logic and force regeneration
- Transcript generation with speaker maps
- Keyterms auto-loading
- Language support
- Batch processing
- Error handling
- Logging and statistics

Requirements:
- Docker and Docker Compose installed
- Deepgram API key in .env file
- Test media files in test_data/ directory
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import time

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class CLITestRunner:
    """Comprehensive test runner for CLI functionality"""
    
    def __init__(self, test_data_dir: str = "test_data"):
        self.test_data_dir = Path(test_data_dir).resolve()
        self.project_root = Path(__file__).parent.parent.resolve()
        self.results = []
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        self.skipped_tests = 0
        self.start_time = None
        self.setup_complete = False
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with color coding"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        if level == "SUCCESS":
            print(f"{Colors.OKGREEN}[{timestamp}] ✓ {message}{Colors.ENDC}")
        elif level == "ERROR":
            print(f"{Colors.FAIL}[{timestamp}] ✗ {message}{Colors.ENDC}")
        elif level == "WARNING":
            print(f"{Colors.WARNING}[{timestamp}] ⚠ {message}{Colors.ENDC}")
        elif level == "HEADER":
            print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
            print(f"{Colors.HEADER}{Colors.BOLD}{message}{Colors.ENDC}")
            print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")
        else:
            print(f"{Colors.OKCYAN}[{timestamp}] ℹ {message}{Colors.ENDC}")
    
    def run_docker_command(self, env_vars: Dict[str, str] = None, 
                          timeout: int = 300) -> Tuple[bool, str, str]:
        """
        Run Docker Compose CLI command with specified environment variables
        
        Returns: (success, stdout, stderr)
        """
        cmd = ["docker", "compose", "run", "--rm"]
        
        # Add environment variables
        if env_vars:
            for key, value in env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])
        
        cmd.extend(["--profile", "cli"])
        cmd.append("cli")
        
        self.log(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)
    
    def verify_file_exists(self, filepath: Path) -> bool:
        """Check if file exists"""
        exists = filepath.exists()
        if exists:
            self.log(f"File exists: {filepath.name}", "SUCCESS")
        else:
            self.log(f"File not found: {filepath}", "ERROR")
        return exists
    
    def verify_file_content(self, filepath: Path, 
                          expected_patterns: List[str] = None) -> bool:
        """Verify file exists and optionally contains expected patterns"""
        if not self.verify_file_exists(filepath):
            return False
        
        if expected_patterns:
            try:
                content = filepath.read_text(encoding='utf-8')
                for pattern in expected_patterns:
                    if pattern not in content:
                        self.log(f"Pattern '{pattern}' not found in {filepath.name}", "ERROR")
                        return False
                self.log(f"All patterns found in {filepath.name}", "SUCCESS")
            except Exception as e:
                self.log(f"Error reading {filepath}: {e}", "ERROR")
                return False
        
        return True
    
    def cleanup_test_outputs(self):
        """Remove all test-generated files"""
        self.log("Cleaning up test outputs...")
        
        patterns_to_remove = [
            "*.srt",
            "*.transcript.speakers.txt",
            "*.deepgram.json",
            "*.synced"
        ]
        
        for pattern in patterns_to_remove:
            for filepath in self.test_data_dir.rglob(pattern):
                try:
                    filepath.unlink()
                    self.log(f"Removed: {filepath.name}")
                except Exception as e:
                    self.log(f"Failed to remove {filepath}: {e}", "WARNING")
        
        # Remove Transcripts directories
        for trans_dir in self.test_data_dir.rglob("Transcripts"):
            try:
                shutil.rmtree(trans_dir)
                self.log(f"Removed directory: {trans_dir}")
            except Exception as e:
                self.log(f"Failed to remove {trans_dir}: {e}", "WARNING")
    
    def record_test_result(self, test_name: str, passed: bool, 
                          message: str = "", skipped: bool = False):
        """Record test result"""
        self.total_tests += 1
        
        if skipped:
            self.skipped_tests += 1
            status = "SKIPPED"
            self.log(f"Test skipped: {test_name} - {message}", "WARNING")
        elif passed:
            self.passed_tests += 1
            status = "PASSED"
            self.log(f"Test passed: {test_name}", "SUCCESS")
        else:
            self.failed_tests += 1
            status = "FAILED"
            self.log(f"Test failed: {test_name} - {message}", "ERROR")
        
        self.results.append({
            "test_name": test_name,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    # ========== TEST SETUP ==========
    
    def test_setup_check(self) -> bool:
        """Verify test environment is properly set up"""
        self.log("TEST: Setup Check", "HEADER")
        
        checks = [
            (self.project_root / ".env", "Environment file (.env)"),
            (self.project_root / "docker-compose.yml", "Docker Compose file"),
            (self.test_data_dir, "Test data directory"),
        ]
        
        all_passed = True
        for path, description in checks:
            if path.exists():
                self.log(f"{description} found", "SUCCESS")
            else:
                self.log(f"{description} not found: {path}", "ERROR")
                all_passed = False
        
        # Check for test videos
        video_dir = self.test_data_dir / "videos"
        if video_dir.exists():
            videos = list(video_dir.glob("*"))
            if videos:
                self.log(f"Found {len(videos)} test files", "SUCCESS")
            else:
                self.log("No test files in videos directory", "WARNING")
                all_passed = False
        else:
            self.log(f"Videos directory not found: {video_dir}", "ERROR")
            all_passed = False
        
        self.record_test_result("Setup Check", all_passed, 
                               "Environment validation")
        self.setup_complete = all_passed
        return all_passed
    
    # ========== CORE TRANSCRIPTION TESTS ==========
    
    def test_basic_video_transcription(self) -> bool:
        """Test 1.1: Basic video transcription"""
        self.log("TEST 1.1: Basic Video Transcription", "HEADER")
        
        if not self.setup_complete:
            self.record_test_result("Basic Video Transcription", False, 
                                   "Setup not complete", skipped=True)
            return False
        
        # Clean up any existing outputs
        self.cleanup_test_outputs()
        
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        if not success:
            self.record_test_result("Basic Video Transcription", False, 
                                   f"Command failed: {stderr}")
            return False
        
        # Check for SRT file
        srt_files = list(self.test_data_dir.rglob("*.eng.srt"))
        if not srt_files:
            self.record_test_result("Basic Video Transcription", False, 
                                   "No SRT file created")
            return False
        
        # Verify SRT format
        srt_file = srt_files[0]
        valid = self.verify_file_content(srt_file, ["-->", "1\n"])
        
        # Check for log file
        log_dir = self.project_root / "deepgram-logs"
        log_files = list(log_dir.glob("deepgram_stats_*.json"))
        
        if log_files:
            log_file = sorted(log_files)[-1]  # Get most recent
            try:
                stats = json.loads(log_file.read_text())
                self.log(f"Processed: {stats.get('processed', 0)} files", "SUCCESS")
                self.log(f"Cost: ${stats.get('estimated_cost', 0):.4f}", "SUCCESS")
            except Exception as e:
                self.log(f"Error reading log: {e}", "WARNING")
        
        self.record_test_result("Basic Video Transcription", valid, 
                               "SRT file created and formatted correctly")
        return valid
    
    def test_skip_existing_srt(self) -> bool:
        """Test 3.1: Skip videos with existing SRT files"""
        self.log("TEST 3.1: Skip Existing SRT", "HEADER")
        
        if not self.setup_complete:
            self.record_test_result("Skip Existing SRT", False, 
                                   "Setup not complete", skipped=True)
            return False
        
        # This test assumes the previous test created an SRT file
        srt_files = list(self.test_data_dir.rglob("*.eng.srt"))
        if not srt_files:
            self.log("No existing SRT files, creating one...", "WARNING")
            # Run transcription first
            self.test_basic_video_transcription()
            srt_files = list(self.test_data_dir.rglob("*.eng.srt"))
        
        if not srt_files:
            self.record_test_result("Skip Existing SRT", False, 
                                   "Could not create SRT for test")
            return False
        
        # Run again without force regenerate
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        # Check if file was skipped
        skipped = "Skipping" in stdout or "skipped" in stdout.lower()
        
        if not skipped:
            self.record_test_result("Skip Existing SRT", False, 
                                   "File was not skipped")
            return False
        
        self.log("File correctly skipped", "SUCCESS")
        self.record_test_result("Skip Existing SRT", True, 
                               "Existing files skipped correctly")
        return True
    
    def test_force_regenerate(self) -> bool:
        """Test 3.2: Force regeneration of existing SRT files"""
        self.log("TEST 3.2: Force Regenerate", "HEADER")
        
        if not self.setup_complete:
            self.record_test_result("Force Regenerate", False, 
                                   "Setup not complete", skipped=True)
            return False
        
        # Ensure SRT exists
        srt_files = list(self.test_data_dir.rglob("*.eng.srt"))
        if not srt_files:
            self.log("Creating initial SRT file...", "INFO")
            self.test_basic_video_transcription()
            srt_files = list(self.test_data_dir.rglob("*.eng.srt"))
        
        if not srt_files:
            self.record_test_result("Force Regenerate", False, 
                                   "Could not create SRT for test")
            return False
        
        srt_file = srt_files[0]
        original_mtime = srt_file.stat().st_mtime
        time.sleep(2)  # Ensure timestamp difference
        
        # Run with force regenerate
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "FORCE_REGENERATE": "1",
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        if not success:
            self.record_test_result("Force Regenerate", False, 
                                   "Command failed")
            return False
        
        # Check if file was regenerated (modified time changed)
        new_mtime = srt_file.stat().st_mtime
        regenerated = new_mtime > original_mtime
        
        if regenerated:
            self.log("SRT file regenerated successfully", "SUCCESS")
        else:
            self.log("SRT file was not regenerated", "ERROR")
        
        self.record_test_result("Force Regenerate", regenerated, 
                               "Existing SRT regenerated")
        return regenerated
    
    # ========== TRANSCRIPT TESTS ==========
    
    def test_transcript_generation(self) -> bool:
        """Test 4.1: Basic transcript generation with speaker diarization"""
        self.log("TEST 4.1: Transcript Generation", "HEADER")
        
        if not self.setup_complete:
            self.record_test_result("Transcript Generation", False, 
                                   "Setup not complete", skipped=True)
            return False
        
        self.cleanup_test_outputs()
        
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "ENABLE_TRANSCRIPT": "1",
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars, timeout=600)
        
        if not success:
            self.record_test_result("Transcript Generation", False, 
                                   "Command failed")
            return False
        
        # Check for transcript file
        transcript_files = list(self.test_data_dir.rglob("*.transcript.speakers.txt"))
        
        if not transcript_files:
            self.record_test_result("Transcript Generation", False, 
                                   "No transcript file created")
            return False
        
        # Verify transcript content
        transcript_file = transcript_files[0]
        valid = self.verify_file_content(transcript_file, ["Speaker"])
        
        # Check for Transcripts folder structure
        transcripts_dir = transcript_file.parent
        if transcripts_dir.name != "Transcripts":
            self.log(f"Transcript not in Transcripts/ folder: {transcripts_dir}", "WARNING")
        
        self.record_test_result("Transcript Generation", valid, 
                               "Transcript created with speaker labels")
        return valid
    
    def test_transcript_with_speaker_map(self) -> bool:
        """Test 4.2: Transcript generation with speaker name mapping"""
        self.log("TEST 4.2: Transcript with Speaker Map", "HEADER")

        # Check if speaker map exists in new Transcripts/Speakermap/ location
        # For TestShow, the speaker map should be at:
        # test_data/videos/TestShow/Transcripts/Speakermap/speakers.csv
        transcripts_dir = self.test_data_dir / "videos" / "TestShow" / "Transcripts" / "Speakermap"
        speaker_csv = transcripts_dir / "speakers.csv"

        if not speaker_csv.exists():
            self.log("No speaker map found, test will use generic labels", "WARNING")
            self.record_test_result("Transcript with Speaker Map", False,
                                   "Speaker map not provided", skipped=True)
            return False

        self.cleanup_test_outputs()

        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "ENABLE_TRANSCRIPT": "1",
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars, timeout=600)
        
        if not success:
            self.record_test_result("Transcript with Speaker Map", False, 
                                   "Command failed")
            return False
        
        # Check transcript for character names (not "Speaker 0")
        transcript_files = list(self.test_data_dir.rglob("*.transcript.speakers.txt"))
        
        if not transcript_files:
            self.record_test_result("Transcript with Speaker Map", False, 
                                   "No transcript created")
            return False
        
        transcript_file = transcript_files[0]
        content = transcript_file.read_text(encoding='utf-8')
        
        # Check if speaker map was applied (should not have "Speaker 0" if map exists)
        has_mapped_names = "Speaker 0" not in content or any(
            name in content for name in ["Character", "Person", "Name"]
        )
        
        if has_mapped_names:
            self.log("Speaker map applied successfully", "SUCCESS")
        else:
            self.log("Speaker map may not have been applied", "WARNING")
        
        self.record_test_result("Transcript with Speaker Map", has_mapped_names, 
                               "Character names used in transcript")
        return has_mapped_names
    
    # ========== KEYTERMS TESTS ==========
    
    def test_keyterms_autoload(self) -> bool:
        """Test 5.1: Auto-load keyterms from CSV"""
        self.log("TEST 5.1: Keyterms Auto-load", "HEADER")
        
        # Check if keyterms CSV exists
        keyterms_files = list(self.test_data_dir.rglob("*_keyterms.csv"))
        
        if not keyterms_files:
            self.log("No keyterms CSV found", "WARNING")
            self.record_test_result("Keyterms Auto-load", False, 
                                   "No keyterms file provided", skipped=True)
            return False
        
        self.cleanup_test_outputs()
        
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        if not success:
            self.record_test_result("Keyterms Auto-load", False, 
                                   "Command failed")
            return False
        
        # Check if keyterms were loaded (look in stdout)
        keyterms_loaded = "keyterms" in stdout.lower() or "Auto-loaded" in stdout
        
        if keyterms_loaded:
            self.log("Keyterms auto-loaded from CSV", "SUCCESS")
        else:
            self.log("No indication keyterms were loaded", "WARNING")
        
        self.record_test_result("Keyterms Auto-load", keyterms_loaded, 
                               "Keyterms detected and loaded")
        return keyterms_loaded
    
    # ========== FILE DISCOVERY TESTS ==========
    
    def test_file_list_processing(self) -> bool:
        """Test 2.3: Process videos from file list"""
        self.log("TEST 2.3: File List Processing", "HEADER")
        
        if not self.setup_complete:
            self.record_test_result("File List Processing", False, 
                                   "Setup not complete", skipped=True)
            return False
        
        # Create file list
        file_list_path = self.test_data_dir / "file_lists" / "test_list.txt"
        file_list_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Find a test video
        videos = list((self.test_data_dir / "videos").glob("*"))
        if not videos:
            self.record_test_result("File List Processing", False, 
                                   "No test videos available")
            return False
        
        # Create file list
        with open(file_list_path, 'w') as f:
            f.write(f"# Test file list\n")
            f.write(f"{videos[0]}\n")
        
        self.cleanup_test_outputs()
        
        env_vars = {
            "FILE_LIST_PATH": str(file_list_path)
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        if not success:
            self.record_test_result("File List Processing", False, 
                                   "Command failed")
            return False
        
        # Check if file from list was processed
        file_processed = "File List" in stdout and "Processing" in stdout
        
        self.record_test_result("File List Processing", file_processed, 
                               "Videos processed from file list")
        return file_processed
    
    # ========== BATCH PROCESSING TESTS ==========
    
    def test_batch_size_limit(self) -> bool:
        """Test 7.1: Batch size limiting"""
        self.log("TEST 7.1: Batch Size Limit", "HEADER")
        
        if not self.setup_complete:
            self.record_test_result("Batch Size Limit", False, 
                                   "Setup not complete", skipped=True)
            return False
        
        # Count available videos
        videos = list((self.test_data_dir / "videos").glob("*"))
        if len(videos) < 2:
            self.log("Need at least 2 test videos", "WARNING")
            self.record_test_result("Batch Size Limit", False, 
                                   "Insufficient test videos", skipped=True)
            return False
        
        self.cleanup_test_outputs()
        
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        if not success:
            self.record_test_result("Batch Size Limit", False, 
                                   "Command failed")
            return False
        
        # Check that only 1 file was processed
        srt_files = list(self.test_data_dir.rglob("*.eng.srt"))
        limited = len(srt_files) == 1
        
        if limited:
            self.log(f"Correctly processed only {len(srt_files)} file(s)", "SUCCESS")
        else:
            self.log(f"Expected 1 file, got {len(srt_files)}", "ERROR")
        
        self.record_test_result("Batch Size Limit", limited, 
                               "Batch size respected")
        return limited
    
    # ========== ERROR HANDLING TESTS ==========
    
    def test_silent_video_handling(self) -> bool:
        """Test 8.1: Handle videos with no speech"""
        self.log("TEST 8.1: Silent Video Handling", "HEADER")
        
        silent_video = self.test_data_dir / "videos" / "silent_test.mp4"
        
        if not silent_video.exists():
            self.log("Silent test video not found", "WARNING")
            self.record_test_result("Silent Video Handling", False, 
                                   "Silent test video not provided", skipped=True)
            return False
        
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        # Should fail gracefully
        handled_gracefully = "No words detected" in stdout or "failed" in stdout.lower()
        
        if handled_gracefully:
            self.log("Silent video handled gracefully", "SUCCESS")
        else:
            self.log("No clear error message for silent video", "WARNING")
        
        self.record_test_result("Silent Video Handling", handled_gracefully, 
                               "Silent video error handled")
        return handled_gracefully
    
    # ========== STATISTICS AND LOGGING TESTS ==========
    
    def test_statistics_generation(self) -> bool:
        """Test 9.1: Statistics JSON generation"""
        self.log("TEST 9.1: Statistics Generation", "HEADER")
        
        if not self.setup_complete:
            self.record_test_result("Statistics Generation", False, 
                                   "Setup not complete", skipped=True)
            return False
        
        log_dir = self.project_root / "deepgram-logs"
        
        # Get log files before test
        existing_logs = set(log_dir.glob("deepgram_stats_*.json"))
        
        self.cleanup_test_outputs()
        
        env_vars = {
            "MEDIA_PATH": str(self.test_data_dir / "videos"),
            "BATCH_SIZE": "1"
        }
        
        success, stdout, stderr = self.run_docker_command(env_vars)
        
        if not success:
            self.record_test_result("Statistics Generation", False, 
                                   "Command failed")
            return False
        
        # Check for new log file
        current_logs = set(log_dir.glob("deepgram_stats_*.json"))
        new_logs = current_logs - existing_logs
        
        if not new_logs:
            self.record_test_result("Statistics Generation", False, 
                                   "No new log file created")
            return False
        
        # Validate JSON structure
        log_file = list(new_logs)[0]
        try:
            stats = json.loads(log_file.read_text())
            required_fields = ["processed", "skipped", "failed", "total_minutes", 
                             "estimated_cost", "model", "language"]
            
            has_all_fields = all(field in stats for field in required_fields)
            
            if has_all_fields:
                self.log("Statistics JSON has all required fields", "SUCCESS")
                self.log(f"  Processed: {stats['processed']}")
                self.log(f"  Cost: ${stats['estimated_cost']:.4f}")
                self.log(f"  Model: {stats['model']}")
            else:
                missing = [f for f in required_fields if f not in stats]
                self.log(f"Missing fields: {missing}", "ERROR")
            
            self.record_test_result("Statistics Generation", has_all_fields, 
                                   "Stats JSON created with all fields")
            return has_all_fields
            
        except json.JSONDecodeError as e:
            self.record_test_result("Statistics Generation", False, 
                                   f"Invalid JSON: {e}")
            return False
    
    # ========== REPORTING ==========
    
    def generate_report(self):
        """Generate final test report"""
        self.log("TEST REPORT", "HEADER")
        
        duration = time.time() - self.start_time if self.start_time else 0
        
        print(f"\n{Colors.BOLD}Test Summary:{Colors.ENDC}")
        print(f"  Total Tests:   {self.total_tests}")
        print(f"  {Colors.OKGREEN}Passed:        {self.passed_tests}{Colors.ENDC}")
        print(f"  {Colors.FAIL}Failed:        {self.failed_tests}{Colors.ENDC}")
        print(f"  {Colors.WARNING}Skipped:       {self.skipped_tests}{Colors.ENDC}")
        print(f"  Duration:      {duration:.1f}s")
        
        success_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0
        print(f"  Success Rate:  {success_rate:.1f}%")
        
        # Detailed results
        print(f"\n{Colors.BOLD}Detailed Results:{Colors.ENDC}")
        for result in self.results:
            status_color = (Colors.OKGREEN if result['status'] == 'PASSED' 
                          else Colors.FAIL if result['status'] == 'FAILED'
                          else Colors.WARNING)
            print(f"  {status_color}[{result['status']}]{Colors.ENDC} {result['test_name']}")
            if result['message']:
                print(f"    └─ {result['message']}")
        
        # Save report to file
        report_file = self.project_root / "tests" / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_data = {
            "summary": {
                "total": self.total_tests,
                "passed": self.passed_tests,
                "failed": self.failed_tests,
                "skipped": self.skipped_tests,
                "success_rate": success_rate,
                "duration_seconds": duration
            },
            "results": self.results,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            report_file.write_text(json.dumps(report_data, indent=2))
            self.log(f"Report saved to: {report_file}", "SUCCESS")
        except Exception as e:
            self.log(f"Failed to save report: {e}", "ERROR")
        
        # Return exit code
        return 0 if self.failed_tests == 0 else 1
    
    def run_all_tests(self):
        """Run all test cases"""
        self.start_time = time.time()
        self.log("Starting Comprehensive CLI Tests", "HEADER")
        
        # Setup
        if not self.test_setup_check():
            self.log("Setup failed, aborting tests", "ERROR")
            return self.generate_report()
        
        # Core tests
        self.test_basic_video_transcription()
        self.test_skip_existing_srt()
        self.test_force_regenerate()
        
        # Feature tests
        self.test_transcript_generation()
        self.test_transcript_with_speaker_map()
        self.test_keyterms_autoload()
        
        # Discovery tests
        self.test_file_list_processing()
        
        # Batch processing
        self.test_batch_size_limit()
        
        # Error handling
        self.test_silent_video_handling()
        
        # Logging
        self.test_statistics_generation()
        
        # Generate final report
        return self.generate_report()


def main():
    """Main entry point"""
    print(f"""
{Colors.HEADER}{Colors.BOLD}
╔═══════════════════════════════════════════════════════════════════╗
║   Subgeneratorr - Comprehensive CLI Test Suite     ║
╚═══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
""")
    
    # Parse command line arguments
    test_data_dir = sys.argv[1] if len(sys.argv) > 1 else "test_data"
    
    runner = CLITestRunner(test_data_dir)
    exit_code = runner.run_all_tests()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
