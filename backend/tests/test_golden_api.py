from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.storage.db import create_session_factory, init_db
from app.api.app import create_app
import app.api.app as api_module
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


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/golden-dataset", None),
        ("POST", "/api/v1/golden-dataset/import", None),
        ("GET", "/api/v1/golden-dataset/benchmark", None),
    ],
)
@pytest.mark.parametrize("tenant_header", [None, ""])
def test_golden_endpoints_require_tenant_header(test_app, method, path, body, tenant_header):
    headers = {} if tenant_header is None else {"X-Tenant-Id": tenant_header}

    response = TestClient(test_app).request(
        method,
        path,
        headers=headers,
        json=body,
    )

    assert response.status_code == 401


def test_import_rejects_csv_path_outside_data_directory(test_app):
    repository_root = Path(__file__).resolve().parent.parent.parent
    outside_csv = repository_root / "outside-golden.csv"

    response = TestClient(test_app).post(
        "/api/v1/golden-dataset/import",
        headers={"X-Tenant-Id": "health_campaign"},
        json={"csv_path": str(outside_csv)},
    )

    assert response.status_code == 400


def test_import_rejects_symlink_outside_data_directory(test_app, tmp_path):
    repository_root = Path(__file__).resolve().parent.parent.parent
    data_directory = repository_root / "data"
    link = data_directory / f".{tmp_path.name}-golden-escape.csv"
    target = tmp_path / "outside.csv"
    target.write_text("Call,Correct outcome\n", encoding="utf-8")
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported in this environment")

    try:
        response = TestClient(test_app).post(
            "/api/v1/golden-dataset/import",
            headers={"X-Tenant-Id": "health_campaign"},
            json={"csv_path": str(link)},
        )
    finally:
        link.unlink(missing_ok=True)

    assert response.status_code == 400


def test_import_rejects_default_csv_symlink_outside_data_directory(
    test_app, tmp_path, monkeypatch
):
    repository_root = tmp_path / "repository"
    monkeypatch.setattr(
        api_module,
        "__file__",
        str(repository_root / "backend" / "app" / "api" / "app.py"),
    )
    data_directory = repository_root / "data"
    data_directory.mkdir(parents=True)
    target = tmp_path / "outside.csv"
    target.write_text("Call,Correct outcome\n", encoding="utf-8")
    default_csv = data_directory / "golden_dataset.csv"
    try:
        default_csv.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported in this environment")

    response = TestClient(test_app).post(
        "/api/v1/golden-dataset/import",
        headers={"X-Tenant-Id": "health_campaign"},
    )

    assert response.status_code == 400

