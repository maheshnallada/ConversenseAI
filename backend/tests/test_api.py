from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.api.app import create_app
from app.storage.db import create_session_factory, init_db


def _client():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    return TestClient(create_app(factory))


def _body():
    return {
        "tenant_id": "tenant_001",
        "interaction_id": "interaction_001",
        "schema_version": "1.0",
        "use_case": "health_insurance",
        "interaction_type": "voice",
        "execution": {"input_tokens": 0, "output_tokens": 3, "cost": None},
    }


def test_post_then_get_round_trip():
    client = _client()
    created = client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": "tenant_001"},
        json=_body(),
    )
    assert created.status_code == 201
    assert created.json()["created"] is True
    assert created.json()["interaction"]["execution"]["input_tokens"] == 0
    assert created.json()["interaction"]["execution"]["cost"] is None

    fetched = client.get(
        "/api/v1/interactions/interaction_001",
        headers={"X-Tenant-Id": "tenant_001"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["interaction_id"] == "interaction_001"


def test_retry_returns_200_and_created_false():
    client = _client()
    headers = {"X-Tenant-Id": "tenant_001"}
    assert client.post("/api/v1/interactions", headers=headers, json=_body()).status_code == 201
    replay = client.post("/api/v1/interactions", headers=headers, json=_body())
    assert replay.status_code == 200
    assert replay.json()["created"] is False


def test_conflicting_replay_returns_409():
    client = _client()
    headers = {"X-Tenant-Id": "tenant_001"}
    client.post("/api/v1/interactions", headers=headers, json=_body())
    changed = _body()
    changed["use_case"] = "customer_support"
    conflict = client.post("/api/v1/interactions", headers=headers, json=changed)
    assert conflict.status_code == 409


def test_missing_tenant_header_is_rejected():
    client = _client()
    response = client.post("/api/v1/interactions", json=_body())
    assert response.status_code == 401


def test_tenant_header_must_match_body():
    client = _client()
    response = client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": "tenant_002"},
        json=_body(),
    )
    assert response.status_code == 403


def test_other_tenant_gets_404():
    client = _client()
    client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": "tenant_001"},
        json=_body(),
    )
    response = client.get(
        "/api/v1/interactions/interaction_001",
        headers={"X-Tenant-Id": "tenant_002"},
    )
    assert response.status_code == 404
