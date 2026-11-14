from pathlib import Path
from datetime import datetime, timezone
from app.evaluation.service import EvaluationService
from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.ingestion.service import IngestionService
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.orm import InteractionRow

def test_on_demand_evaluation_existing_call(session_factory):
    envelope = InteractionEnvelope(
        tenant_id="tenant_eval",
        interaction_id="call_01",
        schema_version="1.0",
    )
    with session_factory.begin() as session:
        session.add(
            InteractionRow(
                tenant_id=envelope.tenant_id,
                interaction_id=envelope.interaction_id,
                schema_version=envelope.schema_version,
                payload_json=envelope.model_dump_json(),
                payload_hash="test-hash",
                created_at=datetime.now(timezone.utc),
            )
        )

    class StubRegistry:
        async def evaluate_batches(self, interaction, turns, timeline=None, batch_names=None):
            now = datetime.now(timezone.utc)
            batches = [
                EvaluationBatchRecord(
                    evaluation_id=f"evaluation-{batch_name}",
                    batch_name=batch_name,
                    status="completed",
                    model="test-model",
                    prompt_version="1",
                    schema_version="1",
                    started_at=now,
                    completed_at=now,
                    input_tokens=1,
                    output_tokens=1,
                    raw_output="{}",
                    parsed_output=None,
                    validation={"schema_valid": True, "evidence_valid": True},
                    review_required=False,
                    review_status="not_required",
                    review_reasons=[],
                )
                for batch_name in (
                    "conversation_understanding",
                    "conversation_quality",
                    "compliance_appointment",
                )
            ]
            return EvaluationRun(
                run_id="run-on-demand",
                tenant_id=interaction.tenant_id,
                interaction_id=interaction.interaction_id,
                batches=batches,
                summary={},
                started_at=now,
                completed_at=now,
                review_required=False,
                review_reasons=[],
            )

    eval_service = EvaluationService(
        session_factory=session_factory,
        registry=StubRegistry(),
    )

    # Resolves call_01 and evaluates
    run = eval_service.evaluate_interaction(
        tenant_id="tenant_eval", interaction_id="call_01"
    )
    assert len(run.batches) == 3

    resolved_id = eval_service.resolve_interaction_id("tenant_eval", "call_01")

    # Verify persisted in database
    eval_repo = EvaluationRepository(session_factory=session_factory)
    saved = eval_repo.get_latest_run(
        tenant_id="tenant_eval", interaction_id=resolved_id
    )
    assert saved is not None
    assert saved.run_id == run.run_id
    assert len(saved.batches) == 3

def test_on_demand_pipeline_new_call_folder(session_factory):
    eval_service = EvaluationService(session_factory=session_factory)
    root = Path(__file__).resolve().parent.parent.parent
    call_folder = root / "backend" / "storage" / "artifacts" / "health_campaign" / "call_03"

    report = eval_service.process_and_evaluate_folder(
        call_folder_path=call_folder,
        tenant_id="health_campaign",
    )

    assert report["folder_name"] == "call_03"
    assert report["turns_count"] > 0
    assert report["timeline_reconstructed"] is True
    assert report["metrics_calculated"] is True
    assert report["evaluations_count"] == 3
    assert "evaluations" in report

    ingestion_service = IngestionService(session_factory)
    assert ingestion_service.outbox_count("health_campaign", report["interaction_id"]) == 1

    eval_service.process_and_evaluate_folder(
        call_folder_path=call_folder,
        tenant_id="health_campaign",
    )
    assert ingestion_service.outbox_count("health_campaign", report["interaction_id"]) == 1
