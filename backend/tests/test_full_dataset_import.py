from pathlib import Path
import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from app.ingestion.batch import BatchImporter
from app.storage.artifacts import LocalArtifactStore
from app.storage.db import create_session_factory, init_db
from app.storage.orm import ArtifactRow, ImportRunRow, InteractionRow, OutboxRow

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "backend" / "storage" / "artifacts" / "health_campaign"


def test_full_50_calls_dataset_import(tmp_path: Path):
    assert CALLS_DIR.exists(), f"Calls directory missing: {CALLS_DIR}"

    factory = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(factory)

    artifact_dir = tmp_path / "artifacts"
    store = LocalArtifactStore(base_dir=artifact_dir)

    importer = BatchImporter(session_factory=factory, artifact_store=store, tenant_id="health_campaign")

    # Run 1: Initial Ingestion of all 50 calls
    result = importer.import_directory(CALLS_DIR, run_id="run_full_initial")

    # Exit criteria validation from Phase 0 inspection and Spec
    assert result.total_calls == 50
    assert result.successful_calls == 50
    assert result.failed_calls == 0
    assert result.newly_created == 50
    assert result.replayed == 0
    assert result.total_artifacts == 672

    # Validate 7 calls without agent manifests
    expected_no_agent = {"call_12", "call_13", "call_25", "call_31", "call_32", "call_43", "call_47"}
    assert set(result.calls_without_agent_manifest) == expected_no_agent

    # Validate 2 digitally silent calls
    expected_silent = {"call_13", "call_25"}
    assert set(result.calls_silent) == expected_silent

    # Validate database state
    with factory() as session:
        interactions_count = session.scalar(select(func.count(InteractionRow.id)))
        assert interactions_count == 50

        outbox_count = session.scalar(select(func.count(OutboxRow.id)))
        assert outbox_count == 50

        artifacts_count = session.scalar(select(func.count(ArtifactRow.id)))
        assert artifacts_count == 672

    # Run 2: Verify Strict Idempotency across the full 50 calls
    replay_result = importer.import_directory(CALLS_DIR, run_id="run_full_replay")

    assert replay_result.total_calls == 50
    assert replay_result.successful_calls == 50
    assert replay_result.failed_calls == 0
    assert replay_result.newly_created == 0
    assert replay_result.replayed == 50

    with factory() as session:
        # DB row counts must remain completely unchanged
        assert session.scalar(select(func.count(InteractionRow.id))) == 50
        assert session.scalar(select(func.count(OutboxRow.id))) == 50
        assert session.scalar(select(func.count(ArtifactRow.id))) == 672
        assert session.scalar(select(func.count(ImportRunRow.id))) == 2

