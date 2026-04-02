import importlib
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Disable auth for tests — the app uses OAuth2-Proxy headers which aren't
# present in the test environment. Tests validate API logic, not auth.
os.environ['DISABLE_AUTH'] = 'true'

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


def test_search_requires_auth():
    """Verify /api/search rejects unauthenticated requests when auth is enabled."""
    with patch.dict(os.environ, {'DISABLE_AUTH': 'false'}, clear=False):
        with app.test_client() as client:
            response = client.get("/api/search?q=test")

    assert response.status_code == 401


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


def test_scan_status_maps_cancelled_payload_to_cancelled_state():
    task_result = SimpleNamespace(
        state="SUCCESS",
        info={
            "cancelled": True,
            "total_scanned": 42,
            "total_missing": 7,
            "scan_time_seconds": 3.2,
        },
    )

    with app.test_client() as client, patch.object(
        app_module.celery_app, "AsyncResult", return_value=task_result
    ):
        response = client.get(
            "/api/library-scan/status/123e4567-e89b-12d3-a456-426614174000"
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "state": "CANCELLED",
        "cancelled": True,
        "total_scanned": 42,
        "total_missing": 7,
        "scan_time_seconds": 3.2,
    }


def test_scan_status_valid_uuid_collecting_progress_stays_zero_without_total():
    task_result = SimpleNamespace(
        state="PROGRESS",
        info={
            "phase": "collecting",
            "scanned": 237,
            "total": 0,
            "missing_so_far": 0,
        },
    )

    with app.test_client() as client, patch.object(
        app_module.celery_app, "AsyncResult", return_value=task_result
    ):
        response = client.get(
            "/api/library-scan/status/123e4567-e89b-12d3-a456-426614174000"
        )

    assert response.status_code == 200
    assert response.get_json()["state"] == "PROGRESS"
    assert response.get_json()["progress"] == 0


def test_job_status_mixed_results_are_terminal_failure_with_results_payload():
    class FakeChild:
        def __init__(self, task_id, state, result=None, info=None):
            self.id = task_id
            self.state = state
            self._result = result
            self.info = info

        def get(self, propagate=False):
            return self._result

    mixed_group = SimpleNamespace(results=[
        FakeChild(
            "child-success",
            "SUCCESS",
            {
                "status": "ok",
                "filename": "episode1.mkv",
                "video": "/media/Show/episode1.mkv",
            },
        ),
        FakeChild(
            "child-failure",
            "FAILURE",
            RuntimeError("Deepgram request failed"),
        ),
    ])

    celery_result_module = types.ModuleType("celery.result")

    class FakeGroupResult:
        @staticmethod
        def restore(task_id, app=None):
            return mixed_group

    celery_result_module.GroupResult = FakeGroupResult
    celery_module = types.ModuleType("celery")
    celery_module.result = celery_result_module

    with app.test_client() as client, \
        patch.dict(sys.modules, {"celery": celery_module, "celery.result": celery_result_module}), \
        patch.object(app_module, "_redis", SimpleNamespace(get=lambda *_: None)):
        response = client.get("/api/job/mixed-batch-id")

    payload = response.get_json()

    assert response.status_code == 200
    assert payload["state"] == "FAILURE"
    assert payload["data"]["results"] == [
        {
            "status": "ok",
            "filename": "episode1.mkv",
            "video": "/media/Show/episode1.mkv",
            "error": "",
        },
        {
            "status": "error",
            "filename": "",
            "video": "",
            "error": "Deepgram request failed",
        },
    ]
    assert payload["children"] == [
        {
            "id": "child-success",
            "state": "SUCCESS",
            "status": "ok",
            "filename": "episode1.mkv",
            "video": "/media/Show/episode1.mkv",
        },
        {
            "id": "child-failure",
            "state": "FAILURE",
            "status": "error",
            "error": "Deepgram request failed",
        },
    ]


def test_scan_status_valid_uuid_revoked_maps_to_cancelled():
    task_result = SimpleNamespace(state="REVOKED", info=None)

    with app.test_client() as client, patch.object(
        app_module.celery_app, "AsyncResult", return_value=task_result
    ):
        response = client.get(
            "/api/library-scan/status/123e4567-e89b-12d3-a456-426614174000"
        )

    assert response.status_code == 200
    assert response.get_json()["state"] == "CANCELLED"
    assert response.get_json()["cancelled"] is True


def test_scan_status_valid_uuid_cancelled():
    task_result = SimpleNamespace(
        state="SUCCESS",
        info={
            "cancelled": True,
            "missing_files": [],
            "total_scanned": 12,
            "total_missing": 0,
        },
    )

    with app.test_client() as client, patch.object(
        app_module.celery_app, "AsyncResult", return_value=task_result
    ):
        response = client.get(
            "/api/library-scan/status/123e4567-e89b-12d3-a456-426614174000"
        )

    assert response.status_code == 200
    assert response.get_json()["state"] == "CANCELLED"
    assert response.get_json()["cancelled"] is True


def test_scan_export_success_relative_paths():
    task_result = SimpleNamespace(
        state="SUCCESS",
        info={
            "missing_files": [
                {
                    "path": "/media/tv/Show/episode1.mkv",
                    "name": "episode1.mkv",
                    "directory": "/media/tv/Show",
                }
            ]
        },
    )

    with app.test_client() as client, patch.object(
        app_module.celery_app, "AsyncResult", return_value=task_result
    ):
        response = client.get(
            "/api/library-scan/export/123e4567-e89b-12d3-a456-426614174000"
        )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "path,name,directory" in body
    assert "tv/Show/episode1.mkv,episode1.mkv,tv/Show" in body
