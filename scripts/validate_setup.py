#!/usr/bin/env python3
"""
Comprehensive validation script for Subgeneratorr.
Validates project structure, files, and configuration for both CLI and Web UI.
"""

import sys
import os
from pathlib import Path

def check_file(path: str, description: str, required: bool = True) -> bool:
    """Check if a file exists."""
    if Path(path).exists():
        print(f"✅ {description}: {path}")
        return True
    else:
        if required:
            print(f"❌ {description} MISSING: {path}")
        else:
            print(f"⚠️  {description} (optional): {path}")
        return False

def check_directory(path: str, description: str, required: bool = True) -> bool:
    """Check if a directory exists."""
    if Path(path).is_dir():
        print(f"✅ {description}: {path}/")
        return True
    else:
        if required:
            print(f"❌ {description} MISSING: {path}/")
        else:
            print(f"⚠️  {description} (optional): {path}/")
        return False

def check_syntax(module_path: str, description: str) -> bool:
    """Check if a Python file has valid syntax."""
    try:
        with open(module_path, 'r') as f:
            compile(f.read(), module_path, 'exec')
        print(f"✅ {description}: valid syntax")
        return True
    except SyntaxError as e:
        print(f"❌ {description}: SYNTAX ERROR at line {e.lineno}")
        return False
    except Exception as e:
        print(f"❌ {description}: ERROR - {e}")
        return False

def check_executable(path: str, description: str) -> bool:
    """Check if a file is executable."""
    file_path = Path(path)
    if file_path.exists():
        is_exec = os.access(file_path, os.X_OK)
        if is_exec:
            print(f"✅ {description}: executable")
            return True
        else:
            print(f"⚠️  {description}: not executable (may need chmod +x)")
            return True  # Don't fail, just warn
    return False

def main():
    print("=" * 70)
    print("Subgeneratorr - Setup Validation")
    print("=" * 70)
    print()
    
    checks = []
    warnings = []
    
    # ========================================================================
    # Project Structure
    # ========================================================================
    print("📂 Project Structure:")
    checks.append(check_directory("cli", "CLI tool directory"))
    checks.append(check_directory("core", "Core library directory"))
    checks.append(check_directory("web", "Web UI directory"))
    checks.append(check_directory("scripts", "Utility scripts directory"))
    checks.append(check_directory("docs", "Documentation directory"))
    checks.append(check_directory("examples", "Example files directory"))
    checks.append(check_directory("tests", "Test scripts directory"))
    warnings.append(check_directory("deepgram-logs", "Logs directory", required=False))
    print()
    
    # ========================================================================
    # Core Files
    # ========================================================================
    print("🔧 Core Library Files:")
    checks.append(check_file("core/__init__.py", "Core __init__.py"))
    checks.append(check_file("core/transcribe.py", "Core transcription module"))
    print()
    
    # ========================================================================
    # CLI Files
    # ========================================================================
    print("💻 CLI Tool Files:")
    checks.append(check_file("cli/generate_subtitles.py", "Main CLI script"))
    checks.append(check_file("cli/config.py", "CLI configuration"))
    checks.append(check_file("cli/transcript_generator.py", "Transcript generator"))
    checks.append(check_file("cli/Dockerfile", "CLI Dockerfile"))
    checks.append(check_file("cli/entrypoint.sh", "CLI entrypoint script"))
    checks.append(check_file("cli/requirements.txt", "CLI dependencies"))
    print()
    
    # ========================================================================
    # Web UI Files
    # ========================================================================
    print("🌐 Web UI Files:")
    checks.append(check_file("web/app.py", "Flask application"))
    checks.append(check_file("web/tasks.py", "Celery tasks"))
    checks.append(check_file("web/requirements.txt", "Web UI dependencies"))
    checks.append(check_file("web/templates/index.html", "Web UI template"))
    checks.append(check_file("web/static/app.js", "Web UI JavaScript"))
    print()
    
    # ========================================================================
    # Scripts
    # ========================================================================
    print("🛠️  Utility Scripts:")
    checks.append(check_file("scripts/postprocess_subtitles.py", "Subtitle renaming script"))
    checks.append(check_file("scripts/validate_setup.py", "Setup validation script"))
    print()
    
    # ========================================================================
    # Documentation
    # ========================================================================
    print("📚 Documentation Files:")
    checks.append(check_file("docs/technical.md", "Technical documentation"))
    checks.append(check_file("docs/roadmap.md", "Project roadmap"))
    checks.append(check_file("docs/languages.md", "Language support guide"))
    print()
    
    # ========================================================================
    # Examples
    # ========================================================================
    print("📋 Example Files:")
    checks.append(check_file("examples/docker-compose.example.yml", "Docker Compose example"))
    checks.append(check_file("examples/video-list-example.txt", "Video list example"))
    checks.append(check_file("examples/test-video.txt", "Test video list"))
    print()
    
    # ========================================================================
    # Tests
    # ========================================================================
    print("🧪 Test Files:")
    checks.append(check_file("tests/test_single_video.py", "Single video test script"))
    print()
    
    # ========================================================================
    # Configuration Files
    # ========================================================================
    print("⚙️  Configuration Files:")
    checks.append(check_file(".env.example", "Environment variables example"))
    checks.append(check_file(".gitignore", "Git ignore rules"))
    checks.append(check_file("Makefile", "Make commands"))
    checks.append(check_file("README.md", "Main documentation"))
    checks.append(check_file("LICENSE", "License file"))
    print()
    
    # ========================================================================
    # Python Syntax Validation
    # ========================================================================
    print("🐍 Python Syntax Validation:")
    
    # Core
    checks.append(check_syntax("core/transcribe.py", "core/transcribe.py"))
    
    # CLI
    checks.append(check_syntax("cli/generate_subtitles.py", "cli/generate_subtitles.py"))
    checks.append(check_syntax("cli/config.py", "cli/config.py"))
    checks.append(check_syntax("cli/transcript_generator.py", "cli/transcript_generator.py"))
    
    # Web
    checks.append(check_syntax("web/app.py", "web/app.py"))
    checks.append(check_syntax("web/tasks.py", "web/tasks.py"))
    
    # Scripts
    checks.append(check_syntax("scripts/postprocess_subtitles.py", "scripts/postprocess_subtitles.py"))
    checks.append(check_syntax("scripts/validate_setup.py", "scripts/validate_setup.py"))
    
    # Tests
    checks.append(check_syntax("tests/test_single_video.py", "tests/test_single_video.py"))
    print()
    
    # ========================================================================
    # Executable Scripts
    # ========================================================================
    print("🔐 Executable Permissions:")
    check_executable("cli/entrypoint.sh", "CLI entrypoint")
    check_executable("cli/generate_subtitles.py", "CLI main script")
    check_executable("scripts/postprocess_subtitles.py", "Postprocess script")
    check_executable("scripts/validate_setup.py", "Validation script")
    check_executable("tests/test_single_video.py", "Test script")
    print()
    
    # ========================================================================
    # Summary
    # ========================================================================
    print("=" * 70)
    passed = sum(checks)
    total = len(checks)
    
    if passed == total:
        print(f"✅ All critical checks passed! ({passed}/{total})")
        print()
        print("Next Steps:")
        print("1. cp .env.example .env")
        print("2. cp examples/docker-compose.example.yml docker-compose.yml")
        print("3. Edit .env: set DEEPGRAM_API_KEY and MEDIA_PATH")
        print("4. docker compose build")
        print("5. docker compose up -d          (Web UI at http://localhost:5000)")
        print("6. docker compose run --profile cli --rm cli   (CLI tool)")
        print()
        print("Docs: README.md | docs/technical.md | docs/languages.md")
        print()
        return 0
    else:
        print(f"❌ Some checks failed ({passed}/{total} passed)")
        print()
        print("Please fix the errors above before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main())