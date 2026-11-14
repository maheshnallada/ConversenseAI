from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository
from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.evaluation.service import EvaluationService
from app.storage import orm
from app.storage.orm import InteractionRow


def _factory():
    f = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(f)
    return f


def _create_archived_results_table(factory):
    with factory.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE evaluation_results "
                "(id INTEGER PRIMARY KEY, tenant_id TEXT, interaction_id TEXT, "
                "evaluator_id TEXT, evaluator_version TEXT, family TEXT, "
                "method TEXT, label TEXT, score FLOAT, confidence FLOAT, "
                "severity TEXT, review_status TEXT, evidence_json TEXT, "
                "reason TEXT, details_json TEXT, created_at DATETIME)"
            )
        )


def test_archived_evaluation_table_is_unmapped_and_left_intact():
    factory = create_session_factory(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with factory.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE evaluation_results "
                "(id INTEGER PRIMARY KEY, evaluator_id TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_results (evaluator_id) "
                "VALUES ('archived.evaluator')"
            )
        )

    assert not hasattr(orm, "EvaluationResultRow")
    init_db(factory)
    with factory.kw["bind"].connect() as connection:
        row_count = connection.scalar(
            text("SELECT COUNT(*) FROM evaluation_results")
        )
    assert row_count == 1


def _sample_batch(evaluation_id, batch_name="conversation_understanding"):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return EvaluationBatchRecord(
        evaluation_id=evaluation_id,
        batch_name=batch_name,
        status="completed",
        model="test-model",
        prompt_version="1.0.0",
        schema_version="1.0.0",
        started_at=now,
        completed_at=now,
        input_tokens=12,
        output_tokens=7,
        raw_output='{"outcome":{"label":"Not interested"}}',
        parsed_output={"outcome": {"label": "Not interested"}},
        validation={
            "schema_valid": True,
            "evidence_valid": True,
            "issues": [],
        },
        review_required=False,
        review_status="not_required",
        review_reasons=[],
    )


def _sample_run(run_id, evaluation_id, interaction_id="call_batched"):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return EvaluationRun(
        run_id=run_id,
        tenant_id="tenant_eval",
        interaction_id=interaction_id,
        batches=[_sample_batch(evaluation_id)],
        summary={"overall_assessment": "Good"},
        started_at=now,
        completed_at=now,
        review_required=False,
        review_reasons=[],
    )


def test_versioned_run_round_trip_and_tenant_scope():
    repo = EvaluationRepository(_factory())
    run = _sample_run("run-1", "batch-1")

    repo.save_run(run)

    retrieved = repo.get_run("tenant_eval", "call_batched", "run-1")
    assert retrieved is not None
    assert retrieved.run_id == "run-1"
    assert retrieved.batches[0].evaluation_id == "batch-1"
    assert retrieved.batches[0].parsed_output == {
        "outcome": {"label": "Not interested"}
    }
    assert retrieved.batches[0].input_tokens == 12
    assert repo.get_run("other_tenant", "call_batched", "run-1") is None


def test_latest_run_excludes_historical_generic_evaluation_rows():
    factory = _factory()
    repo = EvaluationRepository(factory)
    now = datetime.now(timezone.utc)
    _create_archived_results_table(factory)
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO evaluation_results "
                "(tenant_id, interaction_id, evaluator_id, evaluator_version, "
                "family, method, label, review_status, evidence_json, reason, "
                "details_json, created_at) VALUES "
                "('tenant_eval', 'call_batched', 'legacy.evaluator', '1', "
                "'outcome', 'deterministic', 'legacy', 'PASSED', '[]', "
                "'archived', '{}', :created_at)"
            ),
            {"created_at": now.isoformat()},
        )
    repo.save_run(_sample_run("run-old", "batch-old"))
    repo.save_run(_sample_run("run-new", "batch-new"))

    latest = repo.get_latest_run("tenant_eval", "call_batched")

    assert latest is not None
    assert latest.run_id == "run-new"
    assert {batch.evaluation_id for batch in latest.batches} == {"batch-new"}


def test_distinct_runs_preserve_batch_provenance_for_retries():
    repo = EvaluationRepository(_factory())
    first = _sample_run("run-1", "batch-original")
    retry = _sample_run("run-2", "batch-copied")
    retry.batches[0].source_evaluation_id = "batch-original"

    repo.save_run(first)
    repo.save_run(retry)

    loaded_retry = repo.get_run("tenant_eval", "call_batched", "run-2")
    loaded_original = repo.get_run("tenant_eval", "call_batched", "run-1")
    assert loaded_retry is not None
    assert loaded_original is not None
    assert loaded_retry.batches[0].source_evaluation_id == "batch-original"
    assert loaded_original.batches[0].source_evaluation_id is None


def test_service_retry_only_reruns_failed_batches_and_carries_successes():
    from datetime import datetime, timezone

    factory = _factory()
    envelope = InteractionEnvelope(
        tenant_id="tenant_eval",
        interaction_id="call_retry",
        schema_version="1.0",
    )
    with factory() as session:
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
        session.commit()

    class RetryRegistry:
        def __init__(self):
            self.batch_calls = []

        async def evaluate_batches(
            self,
            interaction,
            turns,
            timeline=None,
            batch_names=None,
        ):
            from datetime import datetime, timezone

            names = (
                batch_names
                if batch_names is not None
                else {
                    "conversation_understanding",
                    "conversation_quality",
                    "compliance_appointment",
                }
            )
            self.batch_calls.append(set(names))
            now = datetime.now(timezone.utc)
            batches = []
            for name in sorted(names):
                batch = _sample_batch(f"{len(self.batch_calls)}-{name}", name)
                batch.batch_name = name
                if name == "conversation_quality" and len(self.batch_calls) == 1:
                    batch.status = "failed"
                    batch.parsed_output = None
                    batch.review_required = True
                    batch.error_type = "LLMRequestError"
                if name == "compliance_appointment":
                    batch.parsed_output = None
                batch.started_at = now
                batch.completed_at = now
                batches.append(batch)
            return EvaluationRun(
                run_id=f"run-{len(self.batch_calls)}",
                tenant_id=interaction.tenant_id,
                interaction_id=interaction.interaction_id,
                batches=batches,
                summary={},
                started_at=now,
                completed_at=now,
                review_required=any(batch.review_required for batch in batches),
                review_reasons=[],
            )

    registry = RetryRegistry()
    service = EvaluationService(factory, registry=registry)
    first = service.evaluate_interaction("tenant_eval", "call_retry")
    second = service.evaluate_interaction(
        "tenant_eval",
        "call_retry",
        retry_from_run_id=first.run_id,
    )

    assert first.run_id != second.run_id
    assert registry.batch_calls == [
        {
            "conversation_understanding",
            "conversation_quality",
            "compliance_appointment",
        },
        {"conversation_quality"},
    ]
    reused = next(
        batch for batch in second.batches
        if batch.batch_name == "conversation_understanding"
    )
    assert reused.source_evaluation_id == "1-conversation_understanding"
    assert reused.evaluation_id != reused.source_evaluation_id
    latest = service.eval_repo.get_latest_run("tenant_eval", "call_retry")
    assert latest is not None
    assert latest.run_id == second.run_id
    assert service.eval_repo.get_latest_run("other_tenant", "call_retry") is None

