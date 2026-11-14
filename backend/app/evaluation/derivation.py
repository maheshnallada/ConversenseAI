import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.timeline import ReconstructedTimeline
from app.evaluation.schemas import AppointmentInterpretation


AppointmentStatus = Literal["VALID", "INVALID", "NOT_EVALUABLE", "NOT_APPLICABLE"]


@dataclass(frozen=True)
class AppointmentValidation:
    status: AppointmentStatus
    valid: bool | None
    reason: str
    appointment_at: datetime | None = None


@dataclass(frozen=True)
class FailureCandidate:
    category: str
    failure_type: str
    time_s: float | None = None
    turn_index: int | None = None
    sequence: int | None = None
    severity: str = "unknown"
    evidence: str = ""


@dataclass(frozen=True)
class FirstFailureSummary:
    status: Literal["known", "unknown", "none"]
    first_failure: FailureCandidate | None
    critical_failures: list[FailureCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationSummary:
    overall_assessment: Literal["Good", "OK", "Bad", "Can't tell"]
    dimension_assessments: dict[str, Any]
    first_failure: FirstFailureSummary
    critical_issues: list[str]
    requires_human_review: bool
    review_reasons: list[str]


def _appointment_rules(rules: Mapping[str, Any]) -> Mapping[str, Any] | None:
    candidate = rules.get("appointment_rules", rules)
    if not isinstance(candidate, Mapping):
        return None
    return candidate


def _as_date(value: date | datetime | str | None, timezone: ZoneInfo) -> date | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(timezone).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone).date()
            return parsed.date()
    return None


def _booked_appointment_at(booking_event: Mapping[str, Any]) -> datetime | None:
    event_type = booking_event.get("event_type")
    if event_type not in {"appointment.booked", "booking.confirmed"}:
        return None
    payload = booking_event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("appointment_at")
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def derive_appointment_validity(
    interpretation: AppointmentInterpretation,
    booking_event: Mapping[str, Any] | None,
    call_date: date | datetime | str | None,
    timezone_name: str | None,
    rules: Mapping[str, Any],
) -> AppointmentValidation:
    if interpretation.appointment_type in {"CALLBACK", "NONE"}:
        return AppointmentValidation(
            status="NOT_APPLICABLE",
            valid=None,
            reason="No expert appointment was interpreted.",
        )
    if interpretation.appointment_type != "EXPERT_CALL":
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Appointment type is unclear.",
        )
    if booking_event is None:
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="No confirmed booking event was supplied.",
        )
    if not isinstance(booking_event, Mapping):
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Booking event has an invalid structure.",
        )

    booked_at = _booked_appointment_at(booking_event)
    if booked_at is None:
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Booking event lacks a recognized type or appointment timestamp.",
        )
    if interpretation.consent_status != "EXPLICIT":
        return AppointmentValidation(
            status="INVALID",
            valid=False,
            reason="A confirmed expert appointment lacks explicit customer consent.",
            appointment_at=booked_at,
        )
    if not timezone_name:
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Timezone is required to validate local appointment time.",
            appointment_at=booked_at,
        )
    try:
        local_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Configured timezone is invalid.",
            appointment_at=booked_at,
        )

    appointment_rules = _appointment_rules(rules)
    if appointment_rules is None:
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Appointment policy is unavailable.",
            appointment_at=booked_at,
        )
    earliest_hour = appointment_rules.get("earliest_hour")
    latest_hour = appointment_rules.get("latest_hour")
    allow_same_day = appointment_rules.get("allow_same_day")
    if (
        type(earliest_hour) is not int
        or type(latest_hour) is not int
        or type(allow_same_day) is not bool
        or not 0 <= earliest_hour < latest_hour <= 24
    ):
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Appointment policy is missing or invalid.",
            appointment_at=booked_at,
        )

    local_appointment = (
        booked_at.replace(tzinfo=local_timezone)
        if booked_at.tzinfo is None
        else booked_at.astimezone(local_timezone)
    )
    if not earliest_hour <= local_appointment.hour < latest_hour:
        return AppointmentValidation(
            status="INVALID",
            valid=False,
            reason=(
                f"Appointment time {local_appointment:%H:%M} is outside the "
                f"allowed local window [{earliest_hour:02d}:00, {latest_hour:02d}:00)."
            ),
            appointment_at=local_appointment,
        )

    local_call_date = _as_date(call_date, local_timezone)
    if local_call_date is None:
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Call date is required to validate the booking date.",
            appointment_at=local_appointment,
        )
    if not allow_same_day and local_appointment.date() == local_call_date:
        return AppointmentValidation(
            status="INVALID",
            valid=False,
            reason="Same-day bookings are disallowed by appointment policy.",
            appointment_at=local_appointment,
        )

    return AppointmentValidation(
        status="VALID",
        valid=True,
        reason="Confirmed appointment satisfies consent, time and date policy.",
        appointment_at=local_appointment,
    )


def _candidate_from_record(record: Any, category: str) -> FailureCandidate:
    if isinstance(record, FailureCandidate):
        return record
    time_s = getattr(record, "time_s", None)
    if type(time_s) not in (int, float) or not math.isfinite(time_s):
        time_s = None
    turn_index = getattr(record, "turn_index", None)
    if type(turn_index) is not int:
        turn_index = None
    severity = getattr(record, "severity", "unknown")
    return FailureCandidate(
        category=category,
        failure_type=str(getattr(record, "failure_type", "unknown")),
        time_s=float(time_s) if time_s is not None else None,
        turn_index=turn_index,
        sequence=getattr(record, "sequence", None),
        severity=severity if isinstance(severity, str) else "unknown",
        evidence=str(getattr(record, "evidence", "")),
    )


def _ordered_candidates(
    candidates: list[FailureCandidate],
) -> list[FailureCandidate] | None:
    if len(candidates) < 2:
        return candidates
    if all(candidate.time_s is not None for candidate in candidates):
        by_time: dict[float, list[FailureCandidate]] = {}
        for candidate in candidates:
            by_time.setdefault(candidate.time_s, []).append(candidate)
        ordered: list[FailureCandidate] = []
        for timestamp in sorted(by_time):
            same_time = by_time[timestamp]
            if len(same_time) > 1:
                line_indexes = [candidate.turn_index for candidate in same_time]
                sequences = [candidate.sequence for candidate in same_time]
                if all(value is not None for value in line_indexes) and len(
                    set(line_indexes)
                ) == len(same_time):
                    same_time.sort(key=lambda candidate: candidate.turn_index)
                elif all(value is not None for value in sequences) and len(
                    set(sequences)
                ) == len(same_time):
                    same_time.sort(key=lambda candidate: candidate.sequence)
                else:
                    return None
            ordered.extend(same_time)
        return ordered

    if all(candidate.turn_index is not None for candidate in candidates):
        return sorted(candidates, key=lambda candidate: candidate.turn_index)
    if all(candidate.sequence is not None for candidate in candidates):
        return sorted(candidates, key=lambda candidate: candidate.sequence)
    return None


def merge_failure_candidates(
    technical: Sequence[Any],
    conversational: Sequence[Any],
    compliance: Sequence[Any],
) -> FirstFailureSummary:
    candidates = [
        *(_candidate_from_record(candidate, "technical") for candidate in technical),
        *(
            _candidate_from_record(candidate, "conversational")
            for candidate in conversational
        ),
        *(_candidate_from_record(candidate, "compliance") for candidate in compliance),
    ]
    critical = [candidate for candidate in candidates if candidate.severity == "critical"]
    if not candidates:
        return FirstFailureSummary("none", None, critical)
    ordered = _ordered_candidates(candidates)
    if ordered is None:
        return FirstFailureSummary("unknown", None, critical)
    return FirstFailureSummary("known", ordered[0], critical)


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, Mapping) else None
    return None


def _quality_assessment(batch: Any) -> tuple[str, list[int | None]]:
    data = _as_mapping(batch)
    if data is None:
        return "Can't tell", []
    quality = data.get("conversation_quality")
    quality_data = _as_mapping(quality) or data
    dimensions = _as_mapping(quality_data.get("dimensions"))
    scores: list[int | None] = []
    if dimensions is not None:
        for value in dimensions.values():
            dimension = _as_mapping(value)
            scores.append(dimension.get("score") if dimension else None)
    elif isinstance(quality_data.get("scores"), list):
        scores = quality_data["scores"]
    if not scores or any(score is None for score in scores):
        return "Can't tell", scores
    if any(type(score) is not int or score < 1 or score > 5 for score in scores):
        return "Can't tell", scores
    if any(score <= 2 for score in scores):
        return "Bad", scores
    if any(score == 3 for score in scores):
        return "OK", scores
    return "Good", scores


def _batch_outcome(batch: Any, key: str) -> Any:
    data = _as_mapping(batch)
    if data is None:
        return None
    outcome = _as_mapping(data.get("outcome"))
    if outcome is not None:
        return outcome.get("label")
    return data.get(key)


def derive_evaluation_summary(
    batch_results: Mapping[str, Any],
    timeline: ReconstructedTimeline | None,
    appointment_validation: AppointmentValidation | None,
) -> EvaluationSummary:
    required_batches = {
        "conversation_understanding",
        "conversation_quality",
        "compliance_appointment",
    }
    all_batches_present = required_batches.issubset(batch_results)
    review_reasons: list[str] = []
    critical_issues: list[str] = []

    quality_assessment, scores = _quality_assessment(
        batch_results.get("conversation_quality")
    )
    understanding = batch_results.get("conversation_understanding")
    compliance = batch_results.get("compliance_appointment")
    compliance_data = _as_mapping(compliance) or {}
    compliance_body = _as_mapping(compliance_data.get("compliance")) or compliance_data
    rule_results = _as_mapping(compliance_body.get("rule_results")) or {}
    for rule_id, rule_value in rule_results.items():
        rule = _as_mapping(rule_value)
        if rule is not None and rule.get("status") == "DETECTED":
            critical_issues.append(f"{rule_id}: {rule.get('reason') or 'detected'}")
        if rule is not None and rule.get("status") == "REVIEW_REQUIRED":
            review_reasons.append(f"{rule_id} requires human review")

    if appointment_validation is None or appointment_validation.status == "NOT_EVALUABLE":
        if appointment_validation is not None:
            review_reasons.append(appointment_validation.reason)
    elif appointment_validation.status == "INVALID":
        critical_issues.append(appointment_validation.reason)
    elif appointment_validation.status == "VALID":
        pass

    technical_failures = (
        [timeline.first_technical_failure]
        if (
            timeline
            and timeline.first_technical_failure
            and timeline.first_technical_failure.failure_type != "LATE_AGENT_OPENING"
        )
        else []
    )
    conversational_failures = (
        [timeline.first_conversational_failure]
        if timeline and timeline.first_conversational_failure
        else []
    )
    compliance_failures = [
        FailureCandidate(
            category="compliance",
            failure_type=rule_id,
            turn_index=(_as_mapping(rule_value) or {}).get("evidence_line"),
            severity="critical",
            evidence=str((_as_mapping(rule_value) or {}).get("reason", "")),
        )
        for rule_id, rule_value in rule_results.items()
        if (
            (_as_mapping(rule_value) or {}).get("status") == "DETECTED"
        )
    ]
    first_failure = merge_failure_candidates(
        technical_failures,
        conversational_failures,
        compliance_failures,
    )

    outcome = _batch_outcome(understanding, "outcome")
    understanding_data = _as_mapping(understanding) or {}
    sentiment_data = _as_mapping(understanding_data.get("sentiment")) or {}
    dimension_assessments = {
        "technical_reliability": (
            "ISSUE"
            if technical_failures
            else "UNKNOWN"
            if timeline is None
            else "GOOD"
        ),
        "compliance": "BAD" if critical_issues else "GOOD",
        "conversation_quality": quality_assessment,
        "customer_experience": sentiment_data.get("label", "UNKNOWN"),
        "business_outcome": outcome or "Can't tell",
        "appointment": (
            appointment_validation.status
            if appointment_validation
            else "NOT_EVALUABLE"
        ),
    }

    if not all_batches_present:
        review_reasons.append("One or more evaluation batches are unavailable")
        overall: Literal["Good", "OK", "Bad", "Can't tell"] = "Can't tell"
    elif critical_issues or quality_assessment == "Bad":
        overall = "Bad"
    elif quality_assessment == "Can't tell":
        overall = "Can't tell"
        review_reasons.append("Conversation quality is not fully evaluable")
    else:
        overall = quality_assessment

    return EvaluationSummary(
        overall_assessment=overall,
        dimension_assessments=dimension_assessments,
        first_failure=first_failure,
        critical_issues=critical_issues,
        requires_human_review=bool(review_reasons or critical_issues),
        review_reasons=review_reasons,
    )
