import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.api.app import create_app
from app.core.logging import StructuredJsonFormatter, TraceLoggingMiddleware, configure_logging, get_logger
from app.domain.envelope import InteractionEnvelope
from app.domain.timeline import ReconstructedTimeline, TimelineEvent
from app.storage.db import create_session_factory, init_db
from app.storage.orm import ArtifactRow, InteractionRow
from app.storage.timeline_repo import TimelineRepository


@pytest.fixture
def app_and_factory():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _insert_interaction(factory, interaction_id, folder_name=None):
    domain_data = {"folder_name": folder_name} if folder_name else {}
    envelope = InteractionEnvelope(
        tenant_id="health_campaign",
        interaction_id=interaction_id,
        schema_version="1.0",
        domain_data=domain_data,
    )
    with factory.begin() as session:
        session.add(
            InteractionRow(
                tenant_id=envelope.tenant_id,
                interaction_id=envelope.interaction_id,
                schema_version=envelope.schema_version,
                payload_json=envelope.model_dump_json(),
                payload_hash=interaction_id,
                created_at=datetime.now(timezone.utc),
            )
        )
    return envelope


def test_timeline_and_audio_resolve_for_persisted_interaction(
    app_and_factory, tmp_path
):
    app, factory = app_and_factory
    envelope = _insert_interaction(factory, "call_18")
    now = datetime.now(timezone.utc)
    TimelineRepository(factory).save_timeline(
        ReconstructedTimeline(
            tenant_id=envelope.tenant_id,
            interaction_id=envelope.interaction_id,
            total_duration_s=12.0,
            agent_turn_count=1,
            customer_turn_count=1,
            overlap_count=0,
            total_overlap_s=0.0,
            events=[
                TimelineEvent(
                    event_id="turn-1",
                    event_type="turn",
                    speaker="agent",
                    start_s=0.0,
                    end_s=2.0,
                    text="Hello",
                )
            ],
        )
    )
    recording = tmp_path / "recording.wav"
    recording.write_bytes(b"wav-data")
    with factory.begin() as session:
        session.add(
            ArtifactRow(
                tenant_id=envelope.tenant_id,
                interaction_id=envelope.interaction_id,
                artifact_id="recording-1",
                artifact_type="recording",
                uri=recording.as_uri(),
                media_type="audio/wav",
                sha256="test-hash",
                byte_size=recording.stat().st_size,
                source_path=str(recording),
                validation_status="valid",
                created_at=now,
            )
        )

    timeline_route = next(r for r in app.routes if r.path == "/api/v1/interactions/{interaction_id}/timeline")
    timeline = timeline_route.endpoint(interaction_id="call_18", tenant_id="health_campaign")
    assert timeline is not None
    assert len(timeline["events"]) > 0
    assert timeline["total_duration_s"] > 0

    audio_route = next(r for r in app.routes if r.path == "/api/v1/interactions/{interaction_id}/audio")
    audio = audio_route.endpoint(interaction_id="call_18", tenant_id="health_campaign")
    assert audio is not None
    assert Path(audio.path) == recording


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
