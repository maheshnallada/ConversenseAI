import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.timeline import ReconstructedTimeline
from app.evaluation_bkp.evidence import is_unqualified_acknowledgement
from app.evaluation_bkp.schemas import AppointmentInterpretation


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


FIRST_THING_WRONG_ENUMS = {
    "NO_AGENT_RESPONSE",
    "LATE_AGENT_RESPONSE",
    "AGENT_AUDIO_NOT_PLAYED",
    "AGENT_AUDIO_CUT_OFF",
    "CUSTOMER_INTERRUPTED_AGENT",
    "LONG_AGENT_RESPONSE_DELAY",
    "AGENT_REPEATED_QUESTION",
    "IGNORED_CUSTOMER_INFORMATION",
    "IRRELEVANT_AGENT_RESPONSE",
    "CONTRADICTORY_AGENT_RESPONSE",
    "POOR_OBJECTION_HANDLING",
    "POLICY_OR_INSURER_PUSHING",
    "PREMIUM_FIGURE_DISCLOSURE",
    "BOOKING_WITHOUT_CONSENT",
    "SENSITIVE_INFORMATION_REQUEST",
    "AI_IDENTITY_DENIAL",
    "INAPPROPRIATE_CLOSING",
    "OTHER",
    "NONE",
    "UNKNOWN",
}

TECH_FAILURE_MAP = {
    "NO_AGENT_AUDIO": "NO_AGENT_RESPONSE",
    "NO_AGENT_AUDIO_PLAYED": "NO_AGENT_RESPONSE",
    "NO_AGENT_RESPONSE": "NO_AGENT_RESPONSE",
    "LATE_AGENT_OPENING": "LATE_AGENT_RESPONSE",
    "LATE_AGENT_RESPONSE": "LATE_AGENT_RESPONSE",
    "AGENT_PLAYBACK_CUT": "AGENT_AUDIO_CUT_OFF",
    "AGENT_AUDIO_CUT_OFF": "AGENT_AUDIO_CUT_OFF",
    "AGENT_LINE_NOT_PLAYED": "AGENT_AUDIO_NOT_PLAYED",
    "AGENT_AUDIO_NOT_PLAYED": "AGENT_AUDIO_NOT_PLAYED",
    "LONG_RESPONSE_DELAY": "LONG_AGENT_RESPONSE_DELAY",
    "LONG_AGENT_RESPONSE_DELAY": "LONG_AGENT_RESPONSE_DELAY",
}

COMPLIANCE_RULE_MAP = {
    "NR001": "POLICY_OR_INSURER_PUSHING",
    "NR002": "PREMIUM_FIGURE_DISCLOSURE",
    "NR003": "OTHER",
    "NR004": "BOOKING_WITHOUT_CONSENT",
    "NR005": "SENSITIVE_INFORMATION_REQUEST",
    "NR006": "AI_IDENTITY_DENIAL",
}

CONVERSATIONAL_MAP = {
    "AGENT_REPEATED_QUESTION": "AGENT_REPEATED_QUESTION",
    "AGENT_REPETITION": "AGENT_REPEATED_QUESTION",
    "REPEATED_QUESTION": "AGENT_REPEATED_QUESTION",
    "IGNORED_CUSTOMER_INFORMATION": "IGNORED_CUSTOMER_INFORMATION",
    "IGNORED_INFORMATION": "IGNORED_CUSTOMER_INFORMATION",
    "IRRELEVANT_AGENT_RESPONSE": "IRRELEVANT_AGENT_RESPONSE",
    "IRRELEVANT_FOLLOWUP": "IRRELEVANT_AGENT_RESPONSE",
    "CONTRADICTORY_AGENT_RESPONSE": "CONTRADICTORY_AGENT_RESPONSE",
    "CONTRADICTORY_RESPONSE": "CONTRADICTORY_AGENT_RESPONSE",
    "POOR_OBJECTION_HANDLING": "POOR_OBJECTION_HANDLING",
    "INAPPROPRIATE_CLOSING": "INAPPROPRIATE_CLOSING",
    "CUSTOMER_INTERRUPTED_AGENT": "CUSTOMER_INTERRUPTED_AGENT",
    "CUSTOMER_INTERRUPTION": "CUSTOMER_INTERRUPTED_AGENT",
    "INTERRUPTION": "CUSTOMER_INTERRUPTED_AGENT",
    "NONE": "NONE",
    "OTHER": "OTHER",
    "UNKNOWN": "UNKNOWN",
}


@dataclass(frozen=True)
class EvaluationSummary:
    overall_assessment: Literal["Good", "OK", "Bad", "Can't tell"]
    dimension_assessments: dict[str, Any]
    first_failure: FirstFailureSummary
    critical_issues: list[str]
    requires_human_review: bool
    review_reasons: list[str]
    what_happened: str = "Can't tell"
    first_thing_wrong_category: str = "NONE"
    first_thing_wrong_line: int | None = None
    first_thing_wrong_description: str | None = None
    first_thing_wrong_what: str | None = None
    technical_failure_category: str = "NONE"
    conversational_failure_category: str = "NONE"
    compliance_failure_category: str = "NONE"


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
    if (
        interpretation.consent_evidence_line is None
        or not interpretation.consent_quote.strip()
        or is_unqualified_acknowledgement(interpretation.consent_quote)
    ):
        return AppointmentValidation(
            status="NOT_EVALUABLE",
            valid=None,
            reason="Explicit customer consent is not supported by clear cited evidence.",
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


def _timeline_failures(timeline: Any, category: str) -> list[Any]:
    return [
        failure
        for failure in getattr(timeline, "failures", ())
        if getattr(
            getattr(failure, "category", None),
            "value",
            getattr(failure, "category", None),
        )
        == category
    ]


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
        for dim_name, value in dimensions.items():
            dimension = _as_mapping(value)
            score = dimension.get("score") if dimension else None
            # Guard against invalid penalty on closing_quality when customer cut/disconnected mid-closing
            if dim_name == "closing_quality" and score is not None and score <= 2 and dimension:
                reason_lower = str(dimension.get("reason", "")).lower()
                if any(kw in reason_lower for kw in (
                    "cut", "customer cut", "customer hung", "hung up", "hang up",
                    "not finalize", "didn't finalize", "did not finalize",
                    "no proper closing", "partially", "mid-sentence", "disconnect"
                )):
                    # When agent thanked the customer or delivered closing but was cut off by customer hangup,
                    # score <= 2 is an unfair penalty on a normal customer disconnect.
                    score = None
            scores.append(score)
    elif isinstance(quality_data.get("scores"), list):
        scores = quality_data["scores"]
    if not scores:
        return "Can't tell", scores
    valid_scores = [s for s in scores if isinstance(s, int) and 1 <= s <= 5]
    if not valid_scores:
        return "Can't tell", scores
    if any(s <= 2 for s in valid_scores):
        return "Bad", scores
    if any(s == 3 for s in valid_scores):
        return "OK", scores
    if len(valid_scores) < len(scores):
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


INTRODUCTORY_ONLY_EXAMPLES = {
    "hello",
    "hello hello",
    "haan",
    "haanji",
    "yes",
    "ji",
    "kaun",
    "kaun bol rahe ho",
    "who is this",
    "kahan se",
    "aawaz nahi aa rahi",
}


def validate_what_happened_guard(
    current_label: str,
    outcome: str | None,
    batch_results: Mapping[str, Any],
    timeline: ReconstructedTimeline | None,
) -> str:
    """
    Deterministic post-LLM validation rule for 'What happened' per Section 5.3:
    1. Check if machine or call screener answered.
    2. Check if no agent speech played.
    3. Check if agent's first words came late (>3s).
    4. Check whether the customer left prematurely vs reached an ending.
    5. If customer left and zero customer speech words: 'Left during first line, said nothing'.
    6. If customer left and customer speech consists only of greeting, identity confirmation,
       caller-id question, or generic acknowledgment: 'Said hello or a few words, then left'.
    7. If customer left after at least one substantive domain answer: 'Gave a real answer, then left before an ending'.
    8. If a terminal outcome/closing was reached: 'Call reached an ending'.
    """
    # 1. Machine or call screener answered
    if outcome in ("Voicemail", "Call screener or machine"):
        return "Machine or call screener answered"

    # 2. Heard nothing from agent / late opening
    if timeline and timeline.first_technical_failure:
        ft = timeline.first_technical_failure.failure_type
        if ft in ("NO_AGENT_AUDIO_PLAYED", "NO_AGENT_AUDIO"):
            return "Heard nothing from the agent"
        if ft == "LATE_AGENT_OPENING" and current_label in ("Can't tell", "Call reached an ending"):
            return "Agent's first words came late (over 3s)"

    # 3. Check customer turns from timeline events
    understanding = _as_mapping(batch_results.get("conversation_understanding")) or {}
    cust_facts = understanding.get("customer_facts") or []
    has_substantive_facts = bool(cust_facts and len(cust_facts) > 0)

    quality = _as_mapping(batch_results.get("conversation_quality")) or {}
    completeness = _as_mapping(quality.get("conversation_completeness")) or {}
    conv_status = completeness.get("conversation_status")

    # Determine if customer left prematurely
    is_premature_exit = (
        outcome in ("No outcome: customer left first", "Can't tell")
        or conv_status in (
            "CUSTOMER_LEFT_DURING_OPENING",
            "CUSTOMER_LEFT_DURING_DISCUSSION",
            "NO_MEANINGFUL_INTERACTION",
        )
    )

    # Collect customer utterances
    customer_texts: list[str] = []
    events = getattr(timeline, "events", None) or []
    customer_turn_count = getattr(timeline, "customer_turn_count", None)
    for ev in events:
        if getattr(ev, "event_type", None) == "turn" and getattr(ev, "speaker", None) == "customer":
            text = getattr(ev, "text", None)
            if text and text.strip():
                customer_texts.append(text.strip())

    if is_premature_exit:
        if customer_turn_count == 0 or (events and not customer_texts):
            return "Left during first line, said nothing"

        if has_substantive_facts:
            return "Gave a real answer, then left before an ending"

        def is_introductory(text: str) -> bool:
            cleaned = "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()
            if cleaned in INTRODUCTORY_ONLY_EXAMPLES:
                return True
            words = cleaned.split()
            if len(words) <= 3 and any(w in INTRODUCTORY_ONLY_EXAMPLES for w in words):
                return True
            if any(kw in cleaned for kw in ("bol raha", "bol rahi", "speaking", "this is", "who is")):
                return True
            return False

        if customer_texts and all(is_introductory(t) for t in customer_texts):
            return "Said hello or a few words, then left"

        if current_label in ("Said hello or a few words, then left", "Gave a real answer, then left before an ending"):
            return current_label

        return current_label

    # Terminal outcome / closing reached
    if outcome in ("Expert call booked", "Call later agreed", "Do not call"):
        return "Call reached an ending"

    if outcome == "Not interested" and conv_status in ("COMPLETED", "OUTCOME_REACHED_BUT_NOT_CLOSED"):
        return "Call reached an ending"

    return current_label


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

    timeline_ordering_unknown = bool(
        timeline
        and (
            getattr(timeline, "technical_failure_ordering_unknown", False)
            or getattr(timeline, "conversational_failure_ordering_unknown", False)
        )
    )
    if timeline_ordering_unknown:
        technical_failures = _timeline_failures(timeline, "technical")
        conversational_failures = _timeline_failures(timeline, "conversational")
    else:
        technical_failures = (
            [timeline.first_technical_failure]
            if (
                timeline
                and timeline.first_technical_failure
                and timeline.first_technical_failure.failure_type
                != "LATE_AGENT_OPENING"
            )
            else []
        )
        conversational_failures = (
            [timeline.first_conversational_failure]
            if timeline and timeline.first_conversational_failure
            else []
        )
    quality = batch_results.get("conversation_quality")
    quality_data = _as_mapping(quality) or {}
    what_happened_data = _as_mapping(quality_data.get("what_happened")) or {}
    what_happened_label: str = str(what_happened_data.get("label") or "Can't tell")

    understanding = batch_results.get("conversation_understanding")
    outcome = _batch_outcome(understanding, "outcome")

    what_happened_label = validate_what_happened_guard(
        what_happened_label, outcome, batch_results, timeline
    )

    # 1. Technical failure candidate
    tech_candidate: FailureCandidate | None = None
    technical_failure_category = "NONE"
    if technical_failures:
        first_tech = technical_failures[0]
        raw_ft = getattr(first_tech, "failure_type", "unknown")
        mapped_tech = TECH_FAILURE_MAP.get(
            raw_ft,
            "OTHER" if raw_ft not in ("NONE", "unknown") else "NONE",
        )
        technical_failure_category = mapped_tech
        if mapped_tech != "NONE":
            tech_candidate = FailureCandidate(
                category="technical",
                failure_type=mapped_tech,
                time_s=getattr(first_tech, "time_s", None),
                turn_index=getattr(first_tech, "turn_index", None),
                severity=getattr(first_tech, "severity", "high"),
                evidence=str(getattr(first_tech, "evidence", "")),
            )

    # 2. Conversational failure candidate
    candidate_data = (
        _as_mapping(quality_data.get("first_thing_wrong"))
        or _as_mapping(quality_data.get("first_thing_wrong_candidate"))
        or {}
    )
    raw_cat = str(candidate_data.get("category", "NONE")).strip().upper()
    candidate_line = candidate_data.get("line")
    candidate_desc = str(
        candidate_data.get("description") or candidate_data.get("reason") or ""
    )
    candidate_quote = str(candidate_data.get("quote", ""))

    mapped_conv = CONVERSATIONAL_MAP.get(raw_cat)
    if mapped_conv is None:
        if raw_cat in FIRST_THING_WRONG_ENUMS:
            mapped_conv = raw_cat
        elif raw_cat not in ("NONE", ""):
            mapped_conv = "OTHER"
        else:
            mapped_conv = "NONE"

    # Special treatment for CUSTOMER_INTERRUPTED_AGENT:
    # only an issue if evidence indicates actual failure
    if mapped_conv == "CUSTOMER_INTERRUPTED_AGENT":
        ev_lower = (candidate_desc + " " + candidate_quote).lower()
        has_issue = any(
            kw in ev_lower
            for kw in (
                "cut",
                "incomplete",
                "unplayed",
                "fail",
                "broken",
                "recover",
                "dropped",
            )
        )
        if not has_issue:
            mapped_conv = "NONE"

    # Special treatment for AGENT_AUDIO_NOT_PLAYED:
    # Only valid if there was a genuine technical failure (not an expected cancellation
    # due to customer disconnect, customer interruption/barge-in, or voicemail)
    if mapped_conv == "AGENT_AUDIO_NOT_PLAYED":
        ev_lower = (candidate_desc + " " + candidate_quote).lower()
        is_cancellation = any(
            kw in ev_lower
            for kw in (
                "disconnect",
                "hung up",
                "hang up",
                "hung_up",
                "cut the call",
                "dropped",
                "left first",
                "interrupted",
                "barge",
                "cancelled",
                "voicemail",
            )
        )
        has_tech_unplayed = any(
            getattr(tf, "failure_type", "") in ("AGENT_LINE_NOT_PLAYED", "AGENT_AUDIO_NOT_PLAYED")
            for tf in technical_failures
        )
        if is_cancellation or not has_tech_unplayed:
            mapped_conv = "NONE"

    # Special treatment for AGENT_AUDIO_CUT_OFF:
    # Only valid if cut disrupted substantive conversation (not when customer disconnected on closing/goodbye)
    if mapped_conv == "AGENT_AUDIO_CUT_OFF":
        ev_lower = (candidate_desc + " " + candidate_quote).lower()
        is_closing_cut = any(
            kw in ev_lower
            for kw in (
                "closing",
                "farewell",
                "thank you",
                "goodbye",
                "thanked the customer",
                "finalize the call",
                "customer cut",
                "customer hung up",
                "customer disconnected",
                "hung up",
                "ended the call",
            )
        )
        if is_closing_cut:
            mapped_conv = "NONE"

    conversational_failure_category = mapped_conv
    conv_candidate: FailureCandidate | None = None
    if mapped_conv != "NONE":
        conv_candidate = FailureCandidate(
            category="conversational",
            failure_type=mapped_conv,
            turn_index=candidate_line,
            severity="medium",
            evidence=candidate_desc or candidate_quote,
        )

    # 3. Compliance failure candidate
    detected_compliance = []
    for rule_id, rule_value in rule_results.items():
        mapping = _as_mapping(rule_value) or {}
        if mapping.get("status") == "DETECTED":
            ev_line = mapping.get("evidence_line")
            rule_enum = COMPLIANCE_RULE_MAP.get(rule_id, "OTHER")
            detected_compliance.append(
                FailureCandidate(
                    category="compliance",
                    failure_type=rule_enum,
                    turn_index=ev_line,
                    severity="critical",
                    evidence=str(mapping.get("reason", "")),
                )
            )

    comp_candidate: FailureCandidate | None = None
    if detected_compliance:
        earliest_comp = min(
            detected_compliance,
            key=lambda c: (c.turn_index if c.turn_index is not None else 999999),
        )
        compliance_failure_category = earliest_comp.failure_type
        comp_candidate = earliest_comp
    else:
        compliance_failure_category = "NONE"

    # Merge candidates chronologically
    active_candidates = [
        c for c in [tech_candidate, conv_candidate, comp_candidate] if c is not None
    ]
    critical_candidates = [
        c for c in active_candidates if c.severity == "critical"
    ]

    if not active_candidates:
        first_failure = FirstFailureSummary("none", None, critical_candidates)
        first_thing_wrong_category = "NONE"
        first_thing_wrong_line = None
        first_thing_wrong_description = "No issue identified."
    elif timeline_ordering_unknown:
        first_failure = FirstFailureSummary("unknown", None, critical_candidates)
        first_thing_wrong_category = "UNKNOWN"
        first_thing_wrong_line = None
        first_thing_wrong_description = "Insufficient evidence to identify the first issue."
    else:
        ordered = _ordered_candidates(active_candidates)
        if ordered is None:
            first_failure = FirstFailureSummary("unknown", None, critical_candidates)
            first_thing_wrong_category = "UNKNOWN"
            first_thing_wrong_line = None
            first_thing_wrong_description = "Insufficient evidence to identify the first issue."
        else:
            earliest = ordered[0]
            first_failure = FirstFailureSummary("known", earliest, critical_candidates)
            first_thing_wrong_category = earliest.failure_type
            first_thing_wrong_line = earliest.turn_index
            first_thing_wrong_description = (
                earliest.evidence or f"First failure: {earliest.failure_type}"
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

    bad_ftw = {
        "AGENT_AUDIO_NOT_PLAYED",
        "AGENT_REPEATED_QUESTION",
        "INAPPROPRIATE_POST_BOOKING_QUESTION",
        "IGNORED_CUSTOMER_INFORMATION",
        "BOOKING_WITHOUT_CONSENT",
        "POLICY_OR_INSURER_PUSHING",
        "PREMIUM_FIGURE_DISCLOSURE",
        "SENSITIVE_INFORMATION_REQUEST",
    }

    if not all_batches_present:
        review_reasons.append("One or more evaluation batches are unavailable")
        overall: Literal["Good", "OK", "Bad", "Can't tell"] = "Can't tell"
    elif (
        what_happened_data.get("label") == "Can't tell"
        and outcome == "Can't tell"
    ) or what_happened_label == "Heard nothing from the agent":
        overall = "Can't tell"
    elif (
        critical_issues
        or quality_assessment == "Bad"
        or (
            first_thing_wrong_category in bad_ftw
            and not (
                what_happened_label == "Call reached an ending"
                and outcome in ("Expert call booked", "Do not call")
            )
        )
    ):
        overall = "Bad"
    elif quality_assessment == "Can't tell":
        overall = "Can't tell"
        completeness = (
            _as_mapping(quality_data.get("conversation_completeness")) or {}
        )
        conv_status = completeness.get("conversation_status")
        if conv_status not in ("NO_MEANINGFUL_INTERACTION", "MACHINE_OR_VOICEMAIL"):
            review_reasons.append("Conversation quality is not fully evaluable")
    elif (
        quality_assessment == "Good"
        and first_thing_wrong_category == "NONE"
        and what_happened_label == "Call reached an ending"
        and not critical_issues
    ):
        overall = "Good"
    elif (
        quality_assessment == "Good"
        and first_thing_wrong_category == "NONE"
        and not critical_issues
    ):
        overall = "Good"
    else:
        overall = "OK"

    return EvaluationSummary(
        overall_assessment=overall,
        dimension_assessments=dimension_assessments,
        first_failure=first_failure,
        critical_issues=critical_issues,
        requires_human_review=bool(review_reasons or critical_issues),
        review_reasons=review_reasons,
        what_happened=what_happened_label,
        first_thing_wrong_category=first_thing_wrong_category,
        first_thing_wrong_line=first_thing_wrong_line,
        first_thing_wrong_description=first_thing_wrong_description,
        first_thing_wrong_what=first_thing_wrong_category,
        technical_failure_category=technical_failure_category,
        conversational_failure_category=conversational_failure_category,
        compliance_failure_category=compliance_failure_category,
    )
