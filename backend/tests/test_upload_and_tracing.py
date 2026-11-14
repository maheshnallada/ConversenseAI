import io
import json
import logging
import shutil
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api.app import UploadFilesRequest, create_app
import app.api.app as api_module
from app.core.logging import StructuredJsonFormatter, TraceLoggingMiddleware, configure_logging, get_logger
from app.storage.db import create_session_factory, init_db


@pytest.fixture
def app_and_factory():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    app = create_app(factory)
    return app, factory


def test_structured_logging_formatter():
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="conversense.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test request processed",
        args=(),
        exc_info=None,
    )
    record.method = "GET"
    record.path = "/api/v1/interactions/call_18/timeline"
    record.status_code = 200
    record.duration_ms = 4.25

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "conversense.test"
    assert parsed["message"] == "Test request processed"
    assert parsed["method"] == "GET"
    assert parsed["path"] == "/api/v1/interactions/call_18/timeline"
    assert parsed["status_code"] == 200
    assert parsed["duration_ms"] == 4.25
    assert "timestamp" in parsed


def test_interactions_list_selector_route(app_and_factory):
    app, _ = app_and_factory
    route = next(r for r in app.routes if r.path == "/api/v1/interactions-list")
    items = route.endpoint(tenant_id="health_campaign")
    assert len(items) >= 50
    assert any(i["folder_name"] == "call_18" for i in items)
    assert any(i["folder_name"] == "call_01" for i in items)


def test_call_18_timeline_and_audio_resolution(app_and_factory):
    app, _ = app_and_factory

    # Verify timeline does not 404 for call_18
    timeline_route = next(r for r in app.routes if r.path == "/api/v1/interactions/{interaction_id}/timeline")
    timeline = timeline_route.endpoint(interaction_id="call_18", tenant_id="health_campaign")
    assert timeline is not None
    assert len(timeline["events"]) > 0
    assert timeline["total_duration_s"] > 0

    # Verify audio streaming endpoint resolves file for call_18
    audio_route = next(r for r in app.routes if r.path == "/api/v1/interactions/{interaction_id}/audio")
    audio = audio_route.endpoint(interaction_id="call_18", tenant_id="health_campaign")
    assert audio is not None
    assert Path(audio.path).exists()


def test_find_call_folder_variants(app_and_factory):
    _, factory = app_and_factory
    from app.evaluation.service import EvaluationService
    svc = EvaluationService(factory)

    for p in ["data/calls/call_01", "call_01", "calls/call_01"]:
        found = svc._find_call_folder(p)
        assert found.exists()
        assert (found / "call.json").exists()


def test_find_call_folder_rejects_existing_directory_outside_trusted_roots(app_and_factory, tmp_path):
    _, factory = app_and_factory
    from app.evaluation.service import EvaluationService

    outside_folder = tmp_path / "call_external"
    outside_folder.mkdir()
    (outside_folder / "call.json").write_text('{"call_id": "external"}', encoding="utf-8")
    service = EvaluationService(factory)

    with pytest.raises(FileNotFoundError):
        service._find_call_folder(outside_folder, tenant_id="health_campaign")


def test_unhandled_exception_response_includes_trace_headers():
    app = FastAPI()
    app.add_middleware(TraceLoggingMiddleware)

    @app.get("/raises")
    def raise_error():
        raise RuntimeError("unexpected failure")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/raises",
        headers={"X-Trace-ID": "trace-test", "X-Request-ID": "request-test"},
    )

    assert response.status_code == 500
    assert response.headers["X-Trace-ID"] == "trace-test"
    assert response.headers["X-Request-ID"] == "request-test"


def test_upload_files_rejects_folder_name_that_escapes_staging(
    app_and_factory, tmp_path, monkeypatch
):
    app, _ = app_and_factory
    monkeypatch.chdir(tmp_path)
    route = next(r for r in app.routes if r.path == "/api/v1/interactions/upload-files")
    request = UploadFilesRequest(
        folder_name="../outside",
        call_json='{"call_id": "should_not_be_written"}',
    )

    with pytest.raises(HTTPException) as exc_info:
        route.endpoint(body=request, tenant_id="test_upload_tenant")

    assert exc_info.value.status_code == 400
    assert not (tmp_path / "backend" / "storage" / "outside" / "call.json").exists()


def test_upload_files_json_endpoint(app_and_factory):
    app, factory = app_and_factory
    route = next(r for r in app.routes if r.path == "/api/v1/interactions/upload-files")

    test_tenant = "test_upload_tenant"
    req = UploadFilesRequest(
        folder_name="test_upload_01",
        call_json=json.dumps({
            "call_id": "test_call_uploaded_001",
            "meta": {"agent": "voice_bot", "usage": {"line": {"connected_s": 15.0}}},
            "disposition": "answered",
            "started_at": "2026-11-14T08:00:00Z",
            "end_reason": "customer_ended",
        }),
        manifest_jsonl='{"event": "start", "time": 0.0}\n{"event": "end", "time": 15.0}\n',
        call_log="2026-11-14 Call started\n2026-11-14 Call ended\n",
        tenant_id=test_tenant,
    )
    staging_dir = api_module.UPLOAD_ROOT / test_tenant / "test_upload_01"
    shutil.rmtree(staging_dir, ignore_errors=True)

    try:
        res = route.endpoint(body=req, tenant_id=test_tenant)
        assert res["success"] is True
        assert "test_call_uploaded_001" in str(res)
        assert res["report"]["evaluations_count"] >= 4
    finally:
        with factory() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM interactions WHERE tenant_id = 'test_upload_tenant'"))
            session.execute(text("DELETE FROM evaluation_results WHERE tenant_id = 'test_upload_tenant'"))
            session.execute(text("DELETE FROM interaction_timelines WHERE tenant_id = 'test_upload_tenant'"))
            session.execute(text("DELETE FROM interaction_turns WHERE tenant_id = 'test_upload_tenant'"))
            session.execute(text("DELETE FROM observability_metrics WHERE tenant_id = 'test_upload_tenant'"))
            session.commit()
        shutil.rmtree(staging_dir, ignore_errors=True)
