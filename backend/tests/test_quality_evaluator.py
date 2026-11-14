from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.domain.timeline import ReconstructedTimeline, TimelineEvent
from app.evaluation.quality import QualityEvaluator
from app.domain.transcript import TranscriptTurn


def _envelope():
    return InteractionEnvelope(
        tenant_id="tenant_quality",
        interaction_id="call_quality",
        schema_version="1.0",
        use_case="health_insurance",
    )


def _timeline(agent_start_s):
    return ReconstructedTimeline(
        tenant_id="tenant_quality",
        interaction_id="call_quality",
        total_duration_s=10.0,
        agent_turn_count=1,
        customer_turn_count=0,
        overlap_count=0,
        total_overlap_s=0.0,
        events=[
            TimelineEvent(
                event_id="turn_0",
                event_type="turn",
                speaker="agent",
                start_s=agent_start_s,
            )
        ],
    )


def _failed_compliance():
    evidence = EvidenceItem(
        source_type="transcript_turn",
        reference_id="turn_0",
        line_index=0,
        text_snippet="OTP",
        reason="Agent requested sensitive data",
    )
    return EvaluationResult(
        tenant_id="tenant_quality",
        interaction_id="call_quality",
        evaluator_id="compliance.never_rules",
        evaluator_version="1.0.0",
        family="compliance",
        method="deterministic",
        label="FAILED",
        score=0.0,
        severity="high",
        review_status="FLAGGED_FOR_REVIEW",
        evidence=[evidence],
    )


def test_delayed_first_agent_speech_changes_quality_and_adds_evidence():
    result = QualityEvaluator().evaluate(
        _envelope(),
        [
            TranscriptTurn(
                "agent_1",
                "call_quality",
                "tenant_quality",
                0,
                "agent",
                "Hello, how can I help?",
                "hello, how can i help?",
            )
        ],
        timeline=_timeline(4.5),
    )

    assert result.label == "OK"
    assert result.score == 0.7
    assert result.evidence
    assert "4.50s" in result.evidence[0].reason


def test_empty_turns_preserve_compliance_hard_failure():
    compliance = _failed_compliance()

    result = QualityEvaluator().evaluate(
        _envelope(),
        [],
        compliance_result=compliance,
    )

    assert result.label == "Bad"
    assert result.score == 0.0
    assert result.severity == "high"
    assert result.review_status == "FLAGGED_FOR_REVIEW"
    assert result.evidence == compliance.evidence


def test_empty_turns_without_compliance_failure_are_cant_tell():
    result = QualityEvaluator().evaluate(_envelope(), [])

    assert result.label == "Can't tell"
