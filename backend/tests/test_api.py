import pytest
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


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/interactions", _body()),
        ("GET", "/api/v1/interactions/interaction_001", None),
        ("GET", "/api/v1/interactions", None),
        ("GET", "/api/v1/interactions/interaction_001/timeline", None),
        ("GET", "/api/v1/interactions/interaction_001/audio", None),
        ("POST", "/api/v1/interactions/interaction_001/evaluate", None),
        ("GET", "/api/v1/interactions/interaction_001/evaluations", None),
        (
            "POST",
            "/api/v1/interactions/interaction_001/reviews",
            {
                "evaluator_id": "outcome.intent",
                "reviewed_label": "Interested",
                "reviewer_name": "Reviewer",
            },
        ),
        ("GET", "/api/v1/interactions/interaction_001/reviews", None),
        ("GET", "/api/v1/analytics/overview", None),
    ],
)
@pytest.mark.parametrize("tenant_header", [None, ""])
def test_all_tenant_scoped_routes_reject_missing_or_empty_header(method, path, body, tenant_header):
    client = _client()
    headers = {} if tenant_header is None else {"X-Tenant-Id": tenant_header}

    response = client.request(method, path, headers=headers, json=body)

    assert response.status_code == 401


def test_tenant_header_must_match_body():
    client = _client()
    response = client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": "tenant_002"},
        json=_body(),
    )
    assert response.status_code == 403


def test_legacy_local_ingestion_and_superseded_analytics_routes_are_removed():
    client = _client()
    routes = {
        (method, route.path)
        for route in client.app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    headers = {"X-Tenant-Id": "tenant_001"}
    for method, path, expected_status in (
        ("POST", "/api/v1/interactions/process-and-evaluate", 405),
        ("POST", "/api/v1/interactions/upload-zip", 405),
        ("POST", "/api/v1/interactions/upload-files", 405),
        ("POST", "/api/v1/interactions/seed-all", 405),
        ("GET", "/api/v1/interactions-list", 404),
        ("GET", "/api/v1/analytics/quality", 404),
        ("GET", "/api/v1/analytics/cost", 404),
        ("GET", "/api/v1/use-cases", 404),
    ):
        assert (method, path) not in routes
        response = client.request(method, path, headers=headers)
        assert response.status_code == expected_status, f"{method} {path} should be unavailable"


def test_canonical_interaction_and_benchmark_routes_remain_available():
    app = create_app(
        create_session_factory(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    )
    routes = {
        (method, route.path)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }

    assert ("POST", "/api/v1/interactions") in routes
    assert ("GET", "/api/v1/interactions") in routes
    assert ("GET", "/api/v1/interactions/{interaction_id}") in routes
    assert ("GET", "/api/v1/interactions/{interaction_id}/observability") in routes
    assert ("GET", "/api/v1/interactions/{interaction_id}/reviews") in routes
    assert ("POST", "/api/v1/interactions/{interaction_id}/artifacts") in routes
    assert ("GET", "/api/v1/golden-dataset/benchmark") in routes
    assert ("GET", "/api/v1/imports/staged-calls") in routes
    assert ("POST", "/api/v1/imports/staged-calls") in routes
    assert ("POST", "/api/v1/imports/upload-calls") in routes


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
