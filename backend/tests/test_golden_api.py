from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.api.app import create_app
from app.storage.golden_repo import GoldenDatasetRepository
from app.domain.golden import GoldenCallLabel

@pytest.fixture
def test_app():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return create_app(factory)

def test_golden_api_routes_registered(test_app):
    routes = [r.path for r in test_app.routes]
    assert "/api/v1/golden-dataset" in routes
    assert "/api/v1/golden-dataset/benchmark" in routes
    assert "/api/v1/golden-dataset/import" in routes

