from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
import app.api.app as api_module
from app.domain.benchmark import BenchmarkReport


@pytest.fixture
def test_app(session_factory):
    return create_app(session_factory)


def test_golden_api_routes_registered(test_app):
    routes = [r.path for r in test_app.routes]
    assert "/api/v1/golden-dataset" in routes
    assert "/api/v1/golden-dataset/benchmark" in routes
    assert "/api/v1/golden-dataset/benchmark/export" in routes
    assert "/api/v1/golden-dataset/import" in routes


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/golden-dataset", None),
        ("POST", "/api/v1/golden-dataset/import", None),
        ("GET", "/api/v1/golden-dataset/benchmark", None),
        ("GET", "/api/v1/golden-dataset/benchmark/export", None),
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


@dataclass
class _RecordResult:
    call_id: str
    evaluation_status: str
    evaluation_run_id: str | None
    reused: bool
    error: str | None


@dataclass
class _ImportResult:
    dataset_hash: str = "dataset-hash"
    records_seen: int = 3
    labels_imported: int = 3
    test_records_excluded: int = 1
    evaluations_created: int = 1
    evaluations_reused: int = 0
    evaluations_failed: int = 1
    records: list[_RecordResult] | None = None
    report: BenchmarkReport | None = None

    def __post_init__(self):
        if self.records is None:
            self.records = [
                _RecordResult("call_true", "excluded", None, False, None),
                _RecordResult("call_unknown", "ready", "run-1", False, None),
                _RecordResult("call_invalid", "failed", None, False, "Invalid input."),
            ]
        if self.report is None:
            self.report = BenchmarkReport(total_interactions=2)


def _set_repository_root(monkeypatch, root: Path):
    fake_app_path = root / "backend" / "app" / "api" / "app.py"
    monkeypatch.setattr(api_module, "__file__", str(fake_app_path))
    return root / "Conversense_AI_25_Records_Input_and_Golden.csv"


def test_import_uses_repository_root_csv_and_returns_processing_report(
    test_app, tmp_path, monkeypatch
):
    root = tmp_path / "repository"
    default_csv = _set_repository_root(monkeypatch, root)
    default_csv.parent.mkdir(parents=True)
    default_csv.write_text("test data", encoding="utf-8")
    calls = []

    class FakeBenchmarkService:
        def __init__(self, _session_factory):
            pass

        def import_and_benchmark(self, csv_path, tenant_id):
            calls.append((csv_path, tenant_id))
            return _ImportResult()

    monkeypatch.setattr(
        api_module,
        "GoldenDatasetBenchmarkService",
        FakeBenchmarkService,
        raising=False,
    )

    response = TestClient(test_app).post(
        "/api/v1/golden-dataset/import",
        headers={"X-Tenant-Id": "health_campaign"},
    )

    assert response.status_code == 200
    assert calls == [(default_csv, "health_campaign")]
    body = response.json()
    assert body["dataset_hash"] == "dataset-hash"
    assert body["records_seen"] == 3
    assert body["labels_imported"] == 3
    assert body["test_records_excluded"] == 1
    assert body["evaluations_created"] == 1
    assert body["evaluations_reused"] == 0
    assert body["evaluations_failed"] == 1
    assert [record["evaluation_status"] for record in body["records"]] == [
        "excluded",
        "ready",
        "failed",
    ]
    assert body["report"]["total_interactions"] == 2


def test_import_rejects_default_csv_symlink_outside_data_directory(
    test_app, tmp_path, monkeypatch
):
    repository_root = tmp_path / "repository"
    default_csv = _set_repository_root(monkeypatch, repository_root)
    default_csv.parent.mkdir(parents=True)
    target = tmp_path / "outside.csv"
    target.write_text("Call,Correct outcome\n", encoding="utf-8")
    try:
        default_csv.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported in this environment")

    response = TestClient(test_app).post(
        "/api/v1/golden-dataset/import",
        headers={"X-Tenant-Id": "health_campaign"},
    )

    assert response.status_code == 400


def test_benchmark_get_is_read_only_and_uses_repository_root_csv(
    test_app, tmp_path, monkeypatch
):
    root = tmp_path / "repository"
    default_csv = _set_repository_root(monkeypatch, root)
    default_csv.parent.mkdir(parents=True)
    default_csv.write_text("test data", encoding="utf-8")
    calls = []

    class FakeBenchmarkService:
        def __init__(self, _session_factory):
            pass

        def get_benchmark(self, csv_path, tenant_id):
            calls.append(("get", csv_path, tenant_id))
            return BenchmarkReport(total_interactions=1)

        def import_and_benchmark(self, *_args):
            calls.append(("import",))
            raise AssertionError("GET must not import or evaluate.")

    monkeypatch.setattr(
        api_module,
        "GoldenDatasetBenchmarkService",
        FakeBenchmarkService,
        raising=False,
    )

    response = TestClient(test_app).get(
        "/api/v1/golden-dataset/benchmark",
        headers={"X-Tenant-Id": "health_campaign"},
    )

    assert response.status_code == 200
    assert calls == [("get", default_csv, "health_campaign")]
    assert response.json()["total_interactions"] == 1


def test_benchmark_export_csv(test_app, tmp_path, monkeypatch):
    root = tmp_path / "repository"
    default_csv = _set_repository_root(monkeypatch, root)
    default_csv.parent.mkdir(parents=True)
    default_csv.write_text("test data", encoding="utf-8")
    calls = []

    class FakeBenchmarkService:
        def __init__(self, _session_factory):
            pass

        def export_benchmark_csv(self, csv_path, tenant_id):
            calls.append(("export_csv", csv_path, tenant_id))
            return "call_id,pred_what_happened\ncall_1,Call reached an ending\n"

    monkeypatch.setattr(
        api_module,
        "GoldenDatasetBenchmarkService",
        FakeBenchmarkService,
        raising=False,
    )

    response = TestClient(test_app).get(
        "/api/v1/golden-dataset/benchmark/export",
        headers={"X-Tenant-Id": "health_campaign"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")
    assert "call_1,Call reached an ending" in response.text
    assert calls == [("export_csv", default_csv, "health_campaign")]


def test_benchmark_export_json(test_app, tmp_path, monkeypatch):
    root = tmp_path / "repository"
    default_csv = _set_repository_root(monkeypatch, root)
    default_csv.parent.mkdir(parents=True)
    default_csv.write_text("test data", encoding="utf-8")
    calls = []

    sample_record = {
        "call_id": "call_1",
        "evaluation_status": "ready",
        "gold_what_happened": "Call reached an ending",
        "pred_what_happened": "Call reached an ending",
        "what_happened_match": True,
    }

    class FakeBenchmarkService:
        def __init__(self, _session_factory):
            pass

        def get_interaction_evaluations(self, csv_path, tenant_id):
            calls.append(("get_evaluations", csv_path, tenant_id))
            return [sample_record]

    monkeypatch.setattr(
        api_module,
        "GoldenDatasetBenchmarkService",
        FakeBenchmarkService,
        raising=False,
    )

    response = TestClient(test_app).get(
        "/api/v1/golden-dataset/benchmark/export?format=json",
        headers={"X-Tenant-Id": "health_campaign"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["call_id"] == "call_1"
    assert data[0]["what_happened_match"] is True
    assert calls == [("get_evaluations", default_csv, "health_campaign")]


