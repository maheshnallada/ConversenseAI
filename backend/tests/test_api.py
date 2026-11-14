import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool

from app.api.app import create_app
from app.domain.envelope import InteractionEnvelope
from app.storage.db import create_session_factory, init_db


def _setup_app():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    app = create_app(factory)
    post_route = next(r for r in app.routes if r.path == "/api/v1/interactions" and "POST" in r.methods)
    get_route = next(r for r in app.routes if r.path == "/api/v1/interactions/{interaction_id}" and "GET" in r.methods)
    return app, post_route.endpoint, get_route.endpoint


def _envelope():
    return InteractionEnvelope.model_validate({
        "tenant_id": "tenant_001",
        "interaction_id": "interaction_001",
        "schema_version": "1.0",
        "use_case": "health_insurance",
        "interaction_type": "voice",
        "execution": {"input_tokens": 0, "output_tokens": 3, "cost": None},
    })


def test_post_then_get_round_trip():
    app, post_fn, get_fn = _setup_app()
    env = _envelope()
    res = post_fn(body=env, x_tenant_id="tenant_001")
    assert res.status_code == 201

    fetched = get_fn(interaction_id="interaction_001", x_tenant_id="tenant_001")
    assert fetched.interaction_id == "interaction_001"
    assert fetched.execution.input_tokens == 0


def test_retry_returns_200_and_created_false():
    app, post_fn, _ = _setup_app()
    env = _envelope()
    res1 = post_fn(body=env, x_tenant_id="tenant_001")
    assert res1.status_code == 201

    res2 = post_fn(body=env, x_tenant_id="tenant_001")
    assert res2.status_code == 200


def test_conflicting_replay_returns_409():
    app, post_fn, _ = _setup_app()
    env = _envelope()
    post_fn(body=env, x_tenant_id="tenant_001")

    changed = _envelope()
    changed.use_case = "customer_support"
    with pytest.raises(HTTPException) as exc_info:
        post_fn(body=changed, x_tenant_id="tenant_001")
    assert exc_info.value.status_code == 409


def test_missing_tenant_header_is_rejected():
    app, post_fn, _ = _setup_app()
    with pytest.raises(HTTPException) as exc_info:
        post_fn(body=_envelope(), x_tenant_id=None)
    assert exc_info.value.status_code == 401


def test_tenant_header_must_match_body():
    app, post_fn, _ = _setup_app()
    with pytest.raises(HTTPException) as exc_info:
        post_fn(body=_envelope(), x_tenant_id="tenant_002")
    assert exc_info.value.status_code == 403


def test_other_tenant_gets_404():
    app, post_fn, get_fn = _setup_app()
    post_fn(body=_envelope(), x_tenant_id="tenant_001")

    with pytest.raises(HTTPException) as exc_info:
        get_fn(interaction_id="interaction_001", x_tenant_id="tenant_002")
    assert exc_info.value.status_code == 404
