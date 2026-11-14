from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository
from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.evaluation.service import EvaluationService
from app.storage.orm import InteractionRow


def _factory():
    f = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(f)
    return f


def _sample_result(interaction_id="call_01", evaluator_id="compliance.never_rules"):
    evidence = [
        EvidenceItem(
            source_type="transcript_turn",
            reference_id="turn_2",
            line_index=2,
            text_snippet="Maine policy confirm kar di",
            timestamp_s=4.5,
            reason="Customer agreed to callback",
        )
    ]
    return EvaluationResult(
        tenant_id="tenant_eval",
        interaction_id=interaction_id,
        evaluator_id=evaluator_id,
        evaluator_version="1.0.0",
        family="compliance",
        method="deterministic",
        label="PASSED",
        score=1.0,
        confidence=1.0,
        severity="low",
        review_status="PASSED",
        evidence=evidence,
        reason="No compliance rules violated",
    )


def test_save_and_get_evaluation_results():
    factory = _factory()
    repo = EvaluationRepository(factory)

    r1 = _sample_result("call_01", "compliance.never_rules")
    r2 = _sample_result("call_01", "outcome.classifier")
    r2.label = "Expert call booked"
    r2.family = "outcome"

    repo.save_results("tenant_eval", "call_01", [r1, r2])

    retrieved = repo.get_results("tenant_eval", "call_01")
    assert len(retrieved) == 2

    comp = next(r for r in retrieved if r.evaluator_id == "compliance.never_rules")
    assert comp.label == "PASSED"
    assert comp.score == 1.0
    assert len(comp.evidence) == 1
    assert comp.evidence[0].line_index == 2

    # Idempotency: re-saving replaces cleanly
    repo.save_results("tenant_eval", "call_01", [r1, r2])
    retrieved2 = repo.get_results("tenant_eval", "call_01")
    assert len(retrieved2) == 2


def test_query_by_review_status():
    factory = _factory()
    repo = EvaluationRepository(factory)

    flagged = _sample_result("call_02", "compliance.never_rules")
    flagged.label = "FAILED"
    flagged.review_status = "FLAGGED_FOR_REVIEW"
    flagged.severity = "high"

    repo.save_results("tenant_eval", "call_02", [flagged])

    flagged_list = repo.get_flagged_for_review("tenant_eval")
    assert len(flagged_list) == 1
    assert flagged_list[0].interaction_id == "call_02"
    assert flagged_list[0].severity == "high"


def test_concurrent_saves_replace_the_same_evaluation_key(tmp_path):
    database_path = tmp_path / "concurrent-evaluations.sqlite3"
    factory = create_session_factory(f"sqlite:///{database_path}")
    init_db(factory)
    repo = EvaluationRepository(factory)
    barrier = Barrier(2)

    def save_result(label):
        result = _sample_result("call_concurrent")
        result.label = label
        barrier.wait()
        repo.save_results("tenant_eval", "call_concurrent", [result])

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(save_result, "PASSED"),
            executor.submit(save_result, "FAILED"),
        ]
        for future in futures:
            future.result()

    results = repo.get_results("tenant_eval", "call_concurrent")
    assert len(results) == 1
    assert results[0].label in {"PASSED", "FAILED"}


def test_saves_evaluations_with_an_atomic_upsert():
    factory = _factory()
    repo = EvaluationRepository(factory)
    statements = []
    event.listen(
        factory.engine,
        "before_cursor_execute",
        lambda connection, cursor, statement, parameters, context, executemany:
            statements.append(statement),
    )

    repo.save_results("tenant_eval", "call_01", [_sample_result()])

    writes = [statement.upper() for statement in statements]
    assert any("INSERT INTO EVALUATION_RESULTS" in sql and "ON CONFLICT" in sql for sql in writes)


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
    repo.save_results(
        "tenant_eval",
        "call_batched",
        [_sample_result("call_batched", "legacy.evaluator")],
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

