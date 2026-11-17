import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.queue.broker import InMemoryBroker, set_message_broker
from app.queue.dlq import DLQManager
from app.queue.models import QUEUE_GENERAL, QueueMessage
from app.storage.db import create_session_factory, init_db
from app.storage.stage_repo import StageRepository


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test_dlq.db"
    sf = create_session_factory(f"sqlite:///{db_path}")
    init_db(sf)
    return sf


def test_dlq_manager_list_and_replay(session_factory):
    broker = InMemoryBroker()
    dlq = DLQManager(session_factory, broker=broker)
    stage_repo = StageRepository(session_factory)

    tenant_id = "tenant-replay"
    interaction_id = "int-replay-1"

    stage_repo.record_stage_start(tenant_id, interaction_id, "evaluation")
    stage_repo.record_stage_failure(
        tenant_id,
        interaction_id,
        "evaluation",
        error_message="Provider timeout",
        is_dead_letter=True,
    )

    dead_letters = dlq.list_dead_letters(tenant_id=tenant_id)
    assert len(dead_letters) == 1
    assert dead_letters[0]["interaction_id"] == interaction_id
    assert dead_letters[0]["last_error"] == "Provider timeout"

    # Replay
    replayed = dlq.replay_interaction(tenant_id, interaction_id, target_stage="general")
    assert replayed is True

    # Check stage was reset
    stages = stage_repo.get_stages(tenant_id, interaction_id)
    assert stages[0]["status"] == "pending"

    # Message was re-published to general queue
    stats = broker.get_queue_stats()
    assert stats["queues"][QUEUE_GENERAL] == 1


def test_queue_api_endpoints(session_factory):
    broker = InMemoryBroker()
    set_message_broker(broker)

    app = create_app(session_factory)
    client = TestClient(app)

    # 1. Queue stats
    res = client.get("/api/v1/queue/stats", headers={"X-Tenant-ID": "tenant-test"})
    assert res.status_code == 200
    data = res.json()
    assert "queues" in data

    # 2. DLQ list
    res = client.get("/api/v1/queue/dlq", headers={"X-Tenant-ID": "tenant-test"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 3. Stage history
    res = client.get("/api/v1/interactions/call-123/stages", headers={"X-Tenant-ID": "tenant-test"})
    assert res.status_code == 200
    assert res.json()["interaction_id"] == "call-123"
