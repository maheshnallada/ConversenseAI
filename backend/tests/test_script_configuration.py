import json
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import calculate_metrics, evaluate_calls, import_calls, process_transcripts, reconstruct_calls
from app.evaluation.service import EvaluationService


def test_evaluation_service_uses_artifact_root_and_tenant_call_layout(
    session_factory, monkeypatch, tmp_path
):
    artifact_root = tmp_path / "configured-artifacts"
    call_folder = artifact_root / "tenant_a" / "call_01"
    call_folder.mkdir(parents=True)
    (call_folder / "call.json").write_text(
        json.dumps({"call_id": "canonical-call-id"}), encoding="utf-8"
    )
    monkeypatch.setenv("ARTIFACT_STORAGE_PATH", str(artifact_root))

    service = EvaluationService(session_factory, registry=object())

    assert service.artifact_store.base_dir == artifact_root.resolve()
    assert service.resolve_interaction_id("tenant_a", "call_01") == "canonical-call-id"


def test_import_calls_uses_environment_defaults(monkeypatch, tmp_path):
    captured = {}
    fake_result = SimpleNamespace(
        run_id="run_1",
        total_calls=1,
        successful_calls=1,
        failed_calls=0,
        newly_created=1,
        replayed=0,
        total_artifacts=1,
        calls_without_agent_manifest=[],
        calls_silent=[],
    )

    class FakeStore:
        def __init__(self, base_dir):
            captured["artifact_dir"] = Path(base_dir).resolve()

    class FakeImporter:
        def __init__(self, session_factory, artifact_store, tenant_id):
            captured["tenant_id"] = tenant_id

        def import_directory(self, path):
            captured["data_dir"] = path
            return fake_result

    monkeypatch.setenv("TENANT_ID", "tenant_from_env")
    artifact_root = tmp_path / "artifacts"
    (artifact_root / "tenant_from_env").mkdir(parents=True)
    monkeypatch.setenv("ARTIFACT_STORAGE_PATH", str(artifact_root))
    monkeypatch.setattr(import_calls, "create_session_factory", lambda db_url: object())
    monkeypatch.setattr(import_calls, "init_db", lambda factory: None)
    monkeypatch.setattr(import_calls, "LocalArtifactStore", FakeStore)
    monkeypatch.setattr(import_calls, "BatchImporter", FakeImporter)
    monkeypatch.setattr(import_calls, "generate_markdown_report", lambda result: "report")
    monkeypatch.setattr(sys, "argv", ["import_calls.py", "--report-out", str(tmp_path / "report.md")])

    import_calls.main()

    assert captured["tenant_id"] == "tenant_from_env"
    assert captured["artifact_dir"] == artifact_root.resolve()
    assert Path(captured["data_dir"]).resolve() == (
        artifact_root / "tenant_from_env"
    ).resolve()


def test_evaluate_calls_uses_call_id_and_environment_tenant_for_custom_directory(
    monkeypatch, tmp_path
):
    call_folder = tmp_path / "call_folder_name"
    call_folder.mkdir()
    (call_folder / "call.json").write_text(
        json.dumps({"call_id": "canonical-call-id"}), encoding="utf-8"
    )
    captured = []

    class FakeService:
        def __init__(self, session_factory):
            pass

        def evaluate_interaction(self, tenant_id, interaction_id):
            captured.append((tenant_id, interaction_id))
            return []

    monkeypatch.setenv("TENANT_ID", "tenant_from_env")
    monkeypatch.setattr(evaluate_calls, "create_session_factory", lambda db_url: object())
    monkeypatch.setattr(evaluate_calls, "init_db", lambda factory: None)
    monkeypatch.setattr(evaluate_calls, "EvaluationService", FakeService)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_calls.py", "--data-dir", str(tmp_path)],
    )

    evaluate_calls.main()

    assert captured == [("tenant_from_env", "canonical-call-id")]


def test_evaluate_calls_continues_after_a_folder_failure(
    monkeypatch, tmp_path, capsys
):
    for folder_name, call_id in (
        ("call_01", "broken-call-id"),
        ("call_02", "working-call-id"),
    ):
        folder = tmp_path / folder_name
        folder.mkdir()
        (folder / "call.json").write_text(
            json.dumps({"call_id": call_id}), encoding="utf-8"
        )
    captured = []

    class FakeService:
        def __init__(self, session_factory):
            pass

        def evaluate_interaction(self, tenant_id, interaction_id):
            captured.append(interaction_id)
            if interaction_id == "broken-call-id":
                raise RuntimeError("evaluation failed")
            return []

    monkeypatch.setattr(evaluate_calls, "create_session_factory", lambda db_url: object())
    monkeypatch.setattr(evaluate_calls, "init_db", lambda factory: None)
    monkeypatch.setattr(evaluate_calls, "EvaluationService", FakeService)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_calls.py", "--data-dir", str(tmp_path)],
    )

    evaluate_calls.main()

    output = capsys.readouterr().out
    assert captured == ["broken-call-id", "working-call-id"]
    assert "Total Calls Evaluated: 1" in output
    assert "Failed Calls: 1" in output
    assert "call_01: evaluation failed" in output


def test_calculate_metrics_uses_artifact_tenant_default(monkeypatch, tmp_path, capsys):
    artifact_root = tmp_path / "artifacts"
    call_folder = artifact_root / "tenant_from_env" / "call_01"
    call_folder.mkdir(parents=True)
    captured = []
    summary = SimpleNamespace(
        total_interactions=1,
        total_recording_duration_s=0,
        total_telephony_duration_s=0,
        total_turns=0,
        total_agent_turns=0,
        total_customer_turns=0,
        total_overlap_count=0,
        total_overlap_duration_s=0,
        overall_latency_percentiles=SimpleNamespace(
            avg=0, p50=0, p90=0, p95=0, p99=0
        ),
        total_input_tokens=0,
        total_output_tokens=0,
        total_cost=None,
        currency="MIXED",
        cost_by_currency={"USD": 0.01, "EUR": 0.02},
    )

    class FakeService:
        def __init__(self, session_factory, rate_card):
            pass

        def process_call_folder(self, call_folder, tenant_id):
            captured.append((Path(call_folder).resolve(), tenant_id))

    class FakeRepository:
        def __init__(self, session_factory):
            pass

        def get_platform_summary(self, tenant_id):
            return summary

    monkeypatch.setenv("TENANT_ID", "tenant_from_env")
    monkeypatch.setenv("ARTIFACT_STORAGE_PATH", str(artifact_root))
    monkeypatch.setattr(calculate_metrics, "create_session_factory", lambda db_url: object())
    monkeypatch.setattr(calculate_metrics, "init_db", lambda factory: None)
    monkeypatch.setattr(calculate_metrics, "RateCardManager", lambda path: object())
    monkeypatch.setattr(calculate_metrics, "ObservabilityService", FakeService)
    monkeypatch.setattr(calculate_metrics, "ObservabilityRepository", FakeRepository)
    monkeypatch.setattr(sys, "argv", ["calculate_metrics.py"])

    calculate_metrics.main()

    assert captured == [(call_folder.resolve(), "tenant_from_env")]
    assert "Total Estimated Cost: unavailable (MIXED)" in capsys.readouterr().out


def test_process_transcripts_uses_environment_tenant(monkeypatch, tmp_path):
    (tmp_path / "call_01").mkdir()
    captured = []

    class FakeProcessor:
        def process_folder(self, folder, tenant_id):
            captured.append(tenant_id)
            return []

    monkeypatch.setenv("TENANT_ID", "tenant_from_env")
    monkeypatch.setattr(process_transcripts, "create_session_factory", lambda db_url: object())
    monkeypatch.setattr(process_transcripts, "init_db", lambda factory: None)
    monkeypatch.setattr(process_transcripts, "TranscriptRepository", lambda factory: object())
    monkeypatch.setattr(process_transcripts, "TranscriptProcessor", FakeProcessor)
    monkeypatch.setattr(
        sys,
        "argv",
        ["process_transcripts.py", "--data-dir", str(tmp_path)],
    )

    process_transcripts.main()

    assert captured == ["tenant_from_env"]


def test_reconstruct_calls_uses_environment_tenant(monkeypatch, tmp_path):
    artifact_root = tmp_path / "artifacts"
    call_folder = artifact_root / "tenant_from_env" / "call_01"
    call_folder.mkdir(parents=True)
    (call_folder / "call.json").write_text(
        json.dumps({"call_id": "canonical-call-id"}), encoding="utf-8"
    )
    captured = []

    class FakeProcessor:
        def process_folder(self, folder, tenant_id):
            captured.append((Path(folder).resolve(), tenant_id))
            return []

    class FakeReconstructor:
        def reconstruct(self, **kwargs):
            return SimpleNamespace(
                overlap_count=0,
                first_technical_failure=None,
                first_conversational_failure=None,
            )

    class FakeRepository:
        def __init__(self, session_factory):
            pass

        def save_timeline(self, timeline):
            pass

    monkeypatch.setenv("TENANT_ID", "tenant_from_env")
    monkeypatch.setenv("ARTIFACT_STORAGE_PATH", str(artifact_root))
    monkeypatch.setattr(reconstruct_calls, "create_session_factory", lambda db_url: object())
    monkeypatch.setattr(reconstruct_calls, "init_db", lambda factory: None)
    monkeypatch.setattr(reconstruct_calls, "TimelineRepository", FakeRepository)
    monkeypatch.setattr(reconstruct_calls, "TranscriptProcessor", FakeProcessor)
    monkeypatch.setattr(reconstruct_calls, "TimelineReconstructor", FakeReconstructor)
    monkeypatch.setattr(
        reconstruct_calls,
        "validate_call_files",
        lambda folder: SimpleNamespace(agent_wav_count=0),
    )
    monkeypatch.setattr(sys, "argv", ["reconstruct_calls.py"])

    reconstruct_calls.main()

    assert captured == [(call_folder.resolve(), "tenant_from_env")]
