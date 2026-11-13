from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.api.app import create_app, ProcessFolderRequest

@pytest.fixture
def test_app():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return create_app(factory)

def test_api_routes_registered(test_app):
    routes = [r.path for r in test_app.routes]
    assert "/api/v1/interactions" in routes
    assert "/api/v1/interactions/{interaction_id}" in routes
    assert "/api/v1/interactions/{interaction_id}/evaluate" in routes
    assert "/api/v1/interactions/{interaction_id}/evaluations" in routes
    assert "/api/v1/interactions/process-and-evaluate" in routes

