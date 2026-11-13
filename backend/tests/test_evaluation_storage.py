import pytest
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

