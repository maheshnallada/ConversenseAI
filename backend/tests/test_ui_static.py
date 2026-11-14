from pathlib import Path
from sqlalchemy.pool import StaticPool
from app.api.app import create_app
from app.storage.db import create_session_factory, init_db


def test_serve_dashboard_index_html():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    app = create_app(factory)

    # Check that root route exists
    root_route = next((r for r in app.routes if getattr(r, "path", None) == "/"), None)
    assert root_route is not None

    # Call the endpoint directly
    response = root_route.endpoint()
    assert response.status_code == 200
    assert Path(response.path).exists()
    content = Path(response.path).read_text(encoding="utf-8")
    assert "Conversense AI" in content
    assert "id=\"root\"" in content


def test_serve_dashboard_alias():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    app = create_app(factory)

    dash_route = next((r for r in app.routes if getattr(r, "path", None) == "/dashboard"), None)
    assert dash_route is not None

    response = dash_route.endpoint()
    assert response.status_code == 200
    content = Path(response.path).read_text(encoding="utf-8")
    assert "id=\"root\"" in content


def test_static_assets_mounted():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    app = create_app(factory)

    static_mount = next((r for r in app.routes if getattr(r, "path", None) == "/static"), None)
    assert static_mount is not None

    assets_mount = next((r for r in app.routes if getattr(r, "path", None) == "/assets"), None)
    assert assets_mount is not None
