import importlib
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

# Disable auth for tests; these cases validate browse behavior, not OAuth headers.
os.environ["DISABLE_AUTH"] = "true"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _install_app_dependency_stubs():
    if "deepgram" not in sys.modules:
        deepgram = types.ModuleType("deepgram")

        class DeepgramClient:
            pass

        class PrerecordedOptions:
            pass

        deepgram.DeepgramClient = DeepgramClient
        deepgram.PrerecordedOptions = PrerecordedOptions
        sys.modules["deepgram"] = deepgram

    if "deepgram_captions" not in sys.modules:
        deepgram_captions = types.ModuleType("deepgram_captions")
        deepgram_captions.DeepgramConverter = object
        deepgram_captions.srt = object()
        sys.modules["deepgram_captions"] = deepgram_captions

    if "redis" not in sys.modules:
        redis_module = types.ModuleType("redis")

        class DummyRedis:
            def get(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return True

            def setex(self, *args, **kwargs):
                return True

            def exists(self, *args, **kwargs):
                return False

            def delete(self, *args, **kwargs):
                return 0

        redis_module.from_url = lambda *args, **kwargs: DummyRedis()
        sys.modules["redis"] = redis_module

    if "tasks" not in sys.modules:
        tasks_module = types.ModuleType("tasks")

        class DummyControl:
            def revoke(self, *args, **kwargs):
                return None

        class DummyCeleryApp:
            def __init__(self):
                self.control = DummyControl()

            def AsyncResult(self, task_id):
                return SimpleNamespace(state="PENDING", info=None)

        class DummyTask:
            def delay(self, **kwargs):
                return SimpleNamespace(id="00000000-0000-0000-0000-000000000000")

        tasks_module.celery_app = DummyCeleryApp()
        tasks_module.make_batch = lambda *args, **kwargs: None
        tasks_module.generate_keyterms_task = DummyTask()
        tasks_module.library_scan_task = DummyTask()
        sys.modules["tasks"] = tasks_module


_install_app_dependency_stubs()

app_module = importlib.import_module("web.app")
app = app_module.app
app.config.update(TESTING=True)


def test_browse_defaults_to_fast_non_recursive_directory_counts(tmp_path, monkeypatch):
    shows_dir = tmp_path / "Shows"
    nested_media_dir = shows_dir / "Show Name" / "Season 01"
    nested_media_dir.mkdir(parents=True)
    (nested_media_dir / "episode.mkv").write_text("video")

    monkeypatch.setattr(app_module, "MEDIA_ROOT", tmp_path)

    with app.test_client() as client:
        response = client.get(f"/api/browse?path={tmp_path}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["directories"] == [
        {
            "name": "Shows",
            "path": str(shows_dir),
            "video_count": 0,
        }
    ]
