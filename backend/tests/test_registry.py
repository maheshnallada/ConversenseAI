import pytest
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.evaluation.registry import EvaluatorRegistry

def test_evaluator_registry_runs_all():
    registry = EvaluatorRegistry()
    envelope = InteractionEnvelope(
        tenant_id="test_tenant",
        interaction_id="call_reg_1",
        schema_version="1.0",
        use_case="health_insurance",
    )
    turns = [
        TranscriptTurn("t1", "call_reg_1", "test_tenant", 1, "agent", "Hello, calling from PolicyGuru.", "hello"),
        TranscriptTurn("t2", "call_reg_1", "test_tenant", 2, "customer", "I have company insurance in Pune, not interested.", "i have company insurance in pune, not interested."),
        TranscriptTurn("t3", "call_reg_1", "test_tenant", 3, "agent", "Alright, thank you.", "alright, thank you.")
    ]

    results = registry.evaluate_all(envelope, turns)
    assert len(results) == 5

    families = {r.family for r in results}
    assert "compliance" in families
    assert "outcome" in families
    assert "experience" in families
    assert "quality" in families
    assert "facts" in families

    # Check that compliance passed
    comp = next(r for r in results if r.family == "compliance")
    assert comp.label == "PASSED"

    # Check outcome
    outcome = next(r for r in results if r.family == "outcome")
    assert outcome.label == "Not interested"

    # Check facts
    facts = next(r for r in results if r.family == "facts")
    assert facts.details.get("city") == "Pune"
    assert "Company" in facts.details.get("existing_policy", "")

