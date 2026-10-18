"""
Small JSON settings file for UI preferences that should follow the user across
browsers (currently: which languages appear in the dropdowns).

Lives at ``SETTINGS_PATH`` (default ``/logs/subgeneratorr-settings.json``:
``/logs`` is the one persistent, writable volume every shipped compose file
already mounts, so upgrading needs no compose changes). Writes are atomic
(temp file + ``os.replace``) so a crash never leaves a half-written file.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS_PATH = "/logs/subgeneratorr-settings.json"
LANGUAGE_LISTS = ("transcription", "translation")


class SettingsError(ValueError):
    """Invalid settings payload (maps to HTTP 400)."""


def settings_path() -> Path:
    return Path(os.environ.get("SETTINGS_PATH", DEFAULT_SETTINGS_PATH))


def load_settings() -> dict:
    """The whole settings document; ``{}`` when absent or unreadable."""
    path = settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.warning("Ignoring unreadable settings file %s: %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


def load_language_prefs() -> dict:
    """``{"transcription": [...] | None, "translation": [...] | None}`` (None = all)."""
    stored = load_settings().get("languages")
    stored = stored if isinstance(stored, dict) else {}
    prefs = {}
    for kind in LANGUAGE_LISTS:
        value = stored.get(kind)
        ok = isinstance(value, list) and value and all(isinstance(c, str) for c in value)
        prefs[kind] = value if ok else None
    return prefs


def validate_language_list(kind: str, value, allowed: Iterable[str]) -> Optional[List[str]]:
    """Return a de-duplicated list (or None for "all"); raise SettingsError otherwise."""
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(c, str) for c in value):
        raise SettingsError(f"{kind} must be a list of language codes or null")
    allowed = set(allowed)
    unknown = sorted({c for c in value if c not in allowed})
    if unknown:
        raise SettingsError(f"Unknown {kind} language code(s): {', '.join(unknown)}")
    deduped = list(dict.fromkeys(value))
    if not deduped:
        raise SettingsError(f"Keep at least one {kind} language")
    return deduped


def save_language_prefs(prefs: dict) -> dict:
    """Persist validated language prefs, preserving any other settings keys."""
    settings = load_settings()
    settings["languages"] = {kind: prefs.get(kind) for kind in LANGUAGE_LISTS}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2, sort_keys=True)
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; match the app's other files
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return settings["languages"]
