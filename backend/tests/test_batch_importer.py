import json
from pathlib import Path
import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from app.ingestion.batch import BatchImporter
from app.ingestion.report import generate_markdown_report
from app.storage.artifacts import LocalArtifactStore
from app.storage.db import create_session_factory, init_db
from app.storage.orm import ArtifactRow, ImportRunRow, InteractionRow, OutboxRow

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "data" / "calls"


def _factory():
    f = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(f)
    return f


def test_batch_import_subset_and_idempotency(tmp_path: Path):
    factory = _factory()
    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    importer = BatchImporter(session_factory=factory, artifact_store=store, tenant_id="tenant_batch_test")

    # Create dummy calls folder with two calls
    dummy_calls = tmp_path / "test_calls"
    dummy_calls.mkdir()

    # Copy or symlink / use 3 actual calls: call_01, call_12, call_13
    import shutil
    shutil.copytree(CALLS_DIR / "call_01", dummy_calls / "call_01")
    shutil.copytree(CALLS_DIR / "call_12", dummy_calls / "call_12")
    shutil.copytree(CALLS_DIR / "call_13", dummy_calls / "call_13")

    # First run
    result1 = importer.import_directory(dummy_calls, run_id="run_1")
    assert result1.total_calls == 3
    assert result1.successful_calls == 3
    assert result1.failed_calls == 0
    assert result1.newly_created == 3

    # Check DB rows
    with factory() as session:
        interactions = session.scalars(select(InteractionRow)).all()
        assert len(interactions) == 3

        outbox = session.scalars(select(OutboxRow)).all()
        assert len(outbox) == 3

        artifacts = session.scalars(select(ArtifactRow)).all()
        # call_01 (13) + call_12 (6) + call_13 (5) = 24
        assert len(artifacts) == 24

        import_runs = session.scalars(select(ImportRunRow)).all()
        assert len(import_runs) == 1

    # Second run (Idempotency test)
    result2 = importer.import_directory(dummy_calls, run_id="run_2")
    assert result2.total_calls == 3
    assert result2.successful_calls == 3
    assert result2.newly_created == 0  # All replayed!

    with factory() as session:
        # Interactions, outbox, and artifacts must not duplicate
        assert session.scalar(select(func.count(InteractionRow.id))) == 3
        assert session.scalar(select(func.count(OutboxRow.id))) == 3
        assert session.scalar(select(func.count(ArtifactRow.id))) == 24
        assert session.scalar(select(func.count(ImportRunRow.id))) == 2

    # Markdown report generation
    md = generate_markdown_report(result1)
    assert "# Batch Ingestion Report" in md
    assert "call_01" in md
    assert "call_12" in md
    assert "call_13" in md

