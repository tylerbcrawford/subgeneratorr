import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


def test_scan_status_invalid_task_id():
    with app.test_client() as client:
        response = client.get("/api/library-scan/status/not-a-uuid")

    assert response.status_code == 400


def test_scan_cancel_invalid_task_id():
    with app.test_client() as client:
        response = client.post("/api/library-scan/not-a-uuid/cancel")

    assert response.status_code == 400


def test_scan_export_invalid_task_id():
    with app.test_client() as client:
        response = client.get("/api/library-scan/export/not-a-uuid")

    assert response.status_code == 400


def test_scan_status_valid_uuid_pending():
    task_result = SimpleNamespace(state="PENDING", info=None)

    with app.test_client() as client, patch.object(
        app_module.celery_app, "AsyncResult", return_value=task_result
    ) as mock_async_result:
        response = client.get(
            "/api/library-scan/status/123e4567-e89b-12d3-a456-426614174000"
        )

    assert response.status_code == 200
    assert response.get_json() == {"state": "PENDING"}
    mock_async_result.assert_called_once_with(
        "123e4567-e89b-12d3-a456-426614174000"
    )
