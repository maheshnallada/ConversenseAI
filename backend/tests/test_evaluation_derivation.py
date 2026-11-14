from datetime import date
from types import SimpleNamespace

from app.evaluation.derivation import (
    FailureCandidate,
    derive_appointment_validity,
    derive_evaluation_summary,
    merge_failure_candidates,
)
from app.evaluation.schemas import AppointmentInterpretation


def _interpretation(
    appointment_type="EXPERT_CALL",
    consent_status="EXPLICIT",
):
    return AppointmentInterpretation(
        appointment_type=appointment_type,
        consent_status=consent_status,
        consent_evidence_line=4 if consent_status == "EXPLICIT" else None,
        consent_quote="Yes, tomorrow at 11 is fine."
        if consent_status == "EXPLICIT"
        else "",
        agent_proposal_line=3,
        agent_proposal_quote="Can our expert call tomorrow at 11?",
        date_text="tomorrow",
        time_text="11",
        interpreted_date="2026-11-15",
        interpreted_time="11:00",
        interpretation_reason="Test interpretation.",
    )


def _booking(appointment_at):
    return {
        "event_type": "appointment.booked",
        "occurred_at": "2026-11-14T10:00:00+05:30",
        "payload": {"appointment_at": appointment_at},
    }


def _rules(earliest_hour=9, latest_hour=21, allow_same_day=False):
    return {
        "appointment_rules": {
            "earliest_hour": earliest_hour,
            "latest_hour": latest_hour,
            "allow_same_day": allow_same_day,
        }
    }


def test_clear_consent_and_confirmed_booking_are_valid():
    result = derive_appointment_validity(
        _interpretation(),
        _booking("2026-11-15T11:00:00+05:30"),
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert result.status == "VALID"
    assert result.valid is True


def test_ambiguous_okay_consent_does_not_validate_booking():
    result = derive_appointment_validity(
        _interpretation(consent_status="AMBIGUOUS"),
        _booking("2026-11-15T11:00:00+05:30"),
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert result.status == "INVALID"
    assert result.valid is False
    assert "consent" in result.reason.lower()


def test_explicit_consent_without_cited_evidence_is_not_evaluable():
    interpretation = _interpretation().model_copy(
        update={"consent_evidence_line": None, "consent_quote": ""}
    )

    result = derive_appointment_validity(
        interpretation,
        _booking("2026-11-15T11:00:00+05:30"),
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert result.status == "NOT_EVALUABLE"
    assert result.valid is None


def test_explicit_consent_from_unqualified_acknowledgement_is_not_evaluable():
    interpretation = _interpretation().model_copy(
        update={"consent_quote": "Okay."}
    )

    result = derive_appointment_validity(
        interpretation,
        _booking("2026-11-15T11:00:00+05:30"),
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert result.status == "NOT_EVALUABLE"
    assert result.valid is None


def test_callback_is_not_an_expert_appointment():
    result = derive_appointment_validity(
        _interpretation(appointment_type="CALLBACK"),
        None,
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert result.status == "NOT_APPLICABLE"
    assert result.valid is None


def test_mentioned_time_without_actual_booking_event_is_unavailable():
    result = derive_appointment_validity(
        _interpretation(),
        None,
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert result.status == "NOT_EVALUABLE"
    assert result.valid is None


def test_booking_hours_are_nine_inclusive_and_twenty_one_exclusive():
    at_nine = derive_appointment_validity(
        _interpretation(),
        _booking("2026-11-15T09:00:00+05:30"),
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )
    at_twenty_one = derive_appointment_validity(
        _interpretation(),
        _booking("2026-11-15T21:00:00+05:30"),
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert at_nine.status == "VALID"
    assert at_twenty_one.status == "INVALID"


def test_same_day_booking_is_invalid_when_policy_disallows_it():
    result = derive_appointment_validity(
        _interpretation(),
        _booking("2026-11-14T11:00:00+05:30"),
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert result.status == "INVALID"
    assert "same-day" in result.reason.lower()


def test_missing_timezone_or_booking_event_is_not_evaluable():
    without_timezone = derive_appointment_validity(
        _interpretation(),
        _booking("2026-11-15T11:00:00+05:30"),
        date(2026, 11, 14),
        None,
        _rules(),
    )
    without_event = derive_appointment_validity(
        _interpretation(),
        None,
        date(2026, 11, 14),
        "Asia/Kolkata",
        _rules(),
    )

    assert without_timezone.status == "NOT_EVALUABLE"
    assert without_event.status == "NOT_EVALUABLE"


def test_failure_candidates_use_reliable_timestamps_then_line_order():
    technical = FailureCandidate(
        category="technical",
        failure_type="playback_cut",
        time_s=5.0,
        turn_index=8,
        severity="low",
    )
    conversational = FailureCandidate(
        category="conversational",
        failure_type="ignored_information",
        time_s=5.0,
        turn_index=3,
        severity="medium",
    )
    critical_compliance = FailureCandidate(
        category="compliance",
        failure_type="sensitive_information_request",
        time_s=8.0,
        turn_index=2,
        severity="critical",
    )

    result = merge_failure_candidates(
        [technical],
        [conversational],
        [critical_compliance],
    )

    assert result.status == "known"
    assert result.first_failure.failure_type == "ignored_information"
    assert result.first_failure.severity == "medium"
    assert result.critical_failures == [critical_compliance]


def test_failure_candidates_use_original_line_order_without_timestamps():
    later_line = FailureCandidate(
        category="conversational",
        failure_type="later",
        time_s=None,
        turn_index=12,
    )
    earlier_line = FailureCandidate(
        category="technical",
        failure_type="earlier",
        time_s=None,
        turn_index=2,
    )

    result = merge_failure_candidates([later_line], [earlier_line], [])

    assert result.status == "known"
    assert result.first_failure.failure_type == "earlier"


def test_failure_order_is_unknown_without_reliable_chronology():
    technical = FailureCandidate(
        category="technical",
        failure_type="technical",
        time_s=None,
        turn_index=None,
    )
    conversational = FailureCandidate(
        category="conversational",
        failure_type="conversational",
        time_s=None,
        turn_index=None,
    )

    result = merge_failure_candidates([technical], [conversational], [])

    assert result.status == "unknown"
    assert result.first_failure is None


def test_late_agent_opening_metric_alone_is_not_a_failure():
    timeline = SimpleNamespace(
        first_technical_failure=FailureCandidate(
            category="technical",
            failure_type="LATE_AGENT_OPENING",
            time_s=5.0,
            turn_index=1,
        ),
        first_conversational_failure=None,
    )

    result = derive_evaluation_summary(
        batch_results={},
        timeline=timeline,
        appointment_validation=None,
    )

    assert result.first_failure.status == "none"
    assert result.first_failure.first_failure is None


def test_equal_timestamps_with_incomplete_sequence_are_ambiguous():
    with_line = FailureCandidate(
        category="technical",
        failure_type="with_line",
        time_s=5.0,
        turn_index=3,
    )
    without_line = FailureCandidate(
        category="compliance",
        failure_type="without_line",
        time_s=5.0,
    )

    result = merge_failure_candidates([with_line], [], [without_line])

    assert result.status == "unknown"
    assert result.first_failure is None


def test_empty_batch_results_produce_unknown_assessment():
    result = derive_evaluation_summary(
        batch_results={},
        timeline=None,
        appointment_validation=None,
    )

    assert result.overall_assessment == "Can't tell"
    assert result.dimension_assessments["technical_reliability"] == "UNKNOWN"


def test_customer_rejection_alone_does_not_make_overall_assessment_bad():
    result = derive_evaluation_summary(
        batch_results={
            "conversation_understanding": {
                "outcome": {"label": "Not interested"},
                "sentiment": {"label": "Neutral"},
                "emotion": {"label": "Neutral"},
            },
            "conversation_quality": {
                "scores": [4, 4, 4, 4, 4, 4, 4],
            },
            "compliance_appointment": {
                "detected_critical_issues": [],
            },
        },
        timeline=None,
        appointment_validation=None,
    )

    assert result.overall_assessment == "Good"
    assert result.dimension_assessments["business_outcome"] == "Not interested"
