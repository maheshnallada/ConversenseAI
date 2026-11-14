from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool

from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository


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

