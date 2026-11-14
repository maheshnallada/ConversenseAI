from app.domain.transcript import TranscriptTurn
from app.evaluation.evidence import validate_batch_evidence
from app.evaluation.schemas import (
    CustomerFact,
    ConversationUnderstandingResult,
)


def _turn(index, speaker, text):
    return TranscriptTurn(
        turn_id=f"turn-{index}",
        interaction_id="interaction-1",
        tenant_id="tenant-1",
        turn_index=index,
        speaker=speaker,
        raw_text=text,
        normalized_text=text,
    )


def _understanding(
    *,
    outcome_line=None,
    outcome_quote="",
    sentiment_line=None,
    sentiment_quote="",
    emotion_line=None,
    emotion_quote="",
    customer_facts=None,
):
    return ConversationUnderstandingResult(
        outcome={
            "label": "Can't tell",
            "evidence_line": outcome_line,
            "quote": outcome_quote,
            "reason": "Not established.",
        },
        customer_facts=customer_facts or [],
        sentiment={
            "label": "Can't tell",
            "evidence_line": sentiment_line,
            "quote": sentiment_quote,
            "reason": "Not established.",
        },
        emotion={
            "label": "Can't tell",
            "evidence_line": emotion_line,
            "quote": emotion_quote,
            "reason": "Not established.",
        },
    )


def test_exact_original_script_quote_is_valid():
    turns = [_turn(3, "customer", "నాకు policy కావాలి.")]
    result = _understanding(
        sentiment_line=3,
        sentiment_quote="నాకు policy కావాలి",
    )

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.schema_valid is True
    assert report.evidence_valid is True
    assert report.issues == []


def test_case_or_normalized_quote_change_is_rejected():
    turns = [_turn(1, "customer", "I already have insurance.")]
    result = _understanding(
        sentiment_line=1,
        sentiment_quote="i already have insurance",
    )

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.evidence_valid is False
    assert report.review_reasons


def test_unknown_evidence_line_is_rejected():
    turns = [_turn(1, "customer", "Please call me tomorrow.")]
    result = _understanding(outcome_line=99, outcome_quote="Please call me tomorrow.")

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.evidence_valid is False
    assert any("99" in issue for issue in report.issues)


def test_customer_fact_and_sentiment_cannot_cite_agent_turns():
    turns = [_turn(1, "agent", "You said you have insurance.")]
    result = _understanding(
        sentiment_line=1,
        sentiment_quote="You said you have insurance.",
        customer_facts=[
            CustomerFact(
                category="existing_insurance",
                field="has_existing_insurance",
                value=True,
                evidence_line=1,
                quote="You said you have insurance.",
            )
        ],
    )

    report = validate_batch_evidence("conversation_understanding", result, turns)

    assert report.evidence_valid is False
    assert any("customer" in issue.lower() for issue in report.issues)


def test_absent_optional_evidence_is_valid_and_not_fabricated():
    result = _understanding()

    report = validate_batch_evidence("conversation_understanding", result, [])

    assert report.schema_valid is True
    assert report.evidence_valid is True
    assert report.issues == []


def test_wrong_batch_model_is_reported_as_schema_invalid():
    report = validate_batch_evidence(
        "conversation_understanding",
        {},
        [],
    )

    assert report.schema_valid is False
    assert report.evidence_valid is False
    assert report.review_reasons
