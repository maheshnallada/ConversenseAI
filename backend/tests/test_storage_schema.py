from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.storage.db import create_session_factory, init_db
from app.storage.orm import ArtifactRow, ImportRunRow


def _factory():
    f = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(f)
    return f


def test_artifact_row_crud():
    factory = _factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        art = ArtifactRow(
            tenant_id="tenant_001",
            interaction_id="call_01",
            artifact_id="art_01",
            artifact_type="recording",
            uri="file:///path/to/recording.wav",
            media_type="audio/wav",
            sha256="abc123hash",
            byte_size=1024,
            source_path="/original/path/to/recording.wav",
            validation_status="valid",
            validation_details_json='{"channels": 2, "sample_rate": 16000}',
            created_at=now,
        )
        session.add(art)
        session.commit()

    with factory() as session:
        found = session.scalar(
            select(ArtifactRow).where(
                ArtifactRow.tenant_id == "tenant_001",
                ArtifactRow.interaction_id == "call_01",
                ArtifactRow.artifact_id == "art_01",
            )
        )
        assert found is not None
        assert found.artifact_type == "recording"
        assert found.sha256 == "abc123hash"
        assert found.byte_size == 1024
        assert found.validation_status == "valid"


def test_import_run_row_crud():
    factory = _factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        run = ImportRunRow(
            run_id="run_001",
            tenant_id="tenant_001",
            total_calls=50,
            successful_calls=50,
            failed_calls=0,
            summary_json='{"status": "ok"}',
            started_at=now,
            completed_at=now,
        )
        session.add(run)
        session.commit()

    with factory() as session:
        found = session.scalar(select(ImportRunRow).where(ImportRunRow.run_id == "run_001"))
        assert found is not None
        assert found.total_calls == 50
        assert found.successful_calls == 50

