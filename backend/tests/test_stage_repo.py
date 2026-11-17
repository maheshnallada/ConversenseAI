import pytest
from app.storage.db import create_session_factory, init_db
from app.storage.stage_repo import StageRepository


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test_stage.db"
    sf = create_session_factory(f"sqlite:///{db_path}")
    init_db(sf)
    return sf


def test_stage_repository_lifecycle(session_factory):
    repo = StageRepository(session_factory)
    tenant_id = "tenant-stage"
    interaction_id = "int-100"

    # 1. Start stage
    start_row = repo.record_stage_start(tenant_id, interaction_id, "general")
    assert start_row.status == "running"
    assert start_row.started_at is not None
    assert start_row.completed_at is None

    # 2. Complete stage
    success_row = repo.record_stage_success(tenant_id, interaction_id, "general", duration_ms=125.5)
    assert success_row.status == "completed"
    assert success_row.completed_at is not None
    assert success_row.duration_ms == 125.5
    assert success_row.last_error is None

    # 3. Query stages
    stages = repo.get_stages(tenant_id, interaction_id)
    assert len(stages) == 1
    assert stages[0]["stage_name"] == "general"
    assert stages[0]["status"] == "completed"
    assert stages[0]["duration_ms"] == 125.5


def test_stage_repository_failure_and_dead_letter(session_factory):
    repo = StageRepository(session_factory)
    tenant_id = "tenant-fail"
    interaction_id = "int-200"

    repo.record_stage_start(tenant_id, interaction_id, "evaluation")
    fail_row = repo.record_stage_failure(
        tenant_id,
        interaction_id,
        "evaluation",
        error_message="Connection aborted",
        is_dead_letter=True,
    )
    assert fail_row.status == "dead_letter"
    assert fail_row.retry_count == 1
    assert fail_row.last_error == "Connection aborted"
