import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel

from app.domain.transcript import TranscriptTurn
from app.evaluation.schemas import (
    ComplianceAppointmentResult,
    CustomerFact,
    ConversationQualityResult,
    ConversationUnderstandingResult,
)


_BATCH_MODELS: dict[str, type[BaseModel]] = {
    "conversation_understanding": ConversationUnderstandingResult,
    "conversation_quality": ConversationQualityResult,
    "compliance_appointment": ComplianceAppointmentResult,
}


@dataclass(frozen=True)
class ValidationReport:
    schema_valid: bool
    evidence_valid: bool
    issues: list[str]
    review_reasons: list[str]
    sensitive_data_detected: bool = False


_SENSITIVE_IDENTIFIER_LABEL = re.compile(
    r"\b(?:aadhaar|aadhar|uidai|otp|one[-\s]?time password|"
    r"bank(?:\s+(?:account|details|credentials|login))?|"
    r"(?:online|internet) banking|password|passcode|cvv|pin)\b",
    re.IGNORECASE,
)
_PAN_IDENTIFIER = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
_TWELVE_DIGIT_IDENTIFIER = re.compile(r"(?<!\d)(?:\d[\s-]?){11}\d(?!\d)")
_UNQUALIFIED_ACKNOWLEDGEMENTS = {
    "ok",
    "okay",
    "yes",
    "yeah",
    "yep",
    "sure",
    "fine",
    "alright",
    "right",
    "సరే",
    "అవును",
    "हाँ",
    "हां",
    "ठीक है",
    "হ্যাঁ",
    "জি",
    "சரி",
    "ஆம்",
    "ಸರಿ",
    "ಹೌದು",
    "ശരി",
    "അതെ",
    "હા",
    "બરાબર",
    "हो",
    "होय",
}


def _contains_sensitive_customer_identifier(fact: CustomerFact) -> bool:
    text = " ".join(
        str(value)
        for value in (fact.category, fact.field, fact.value, fact.quote)
        if value is not None
    )
    normalized_text = re.sub(r"[_-]+", " ", text)
    if _SENSITIVE_IDENTIFIER_LABEL.search(
        normalized_text
    ) or _PAN_IDENTIFIER.search(text):
        return True

    field = re.sub(r"[_-]+", " ", fact.field)
    identity_field = re.search(
        r"\b(?:identity|national\s+id)\b",
        field,
        re.IGNORECASE,
    )
    value_and_quote = " ".join(str(value) for value in (fact.value, fact.quote))
    return bool(
        identity_field and _TWELVE_DIGIT_IDENTIFIER.search(value_and_quote)
    )


def is_unqualified_acknowledgement(quote: str) -> bool:
    normalized = unicodedata.normalize("NFKC", quote).casefold()
    normalized = " ".join(re.findall(r"\w+", normalized))
    return normalized in _UNQUALIFIED_ACKNOWLEDGEMENTS



def _normalize_for_quote_match(value: str) -> str:
    """Normalize Unicode compatibility forms and whitespace for comparison only."""
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.split())


def _normalized_contains(quote: str, source: str) -> bool:
    q = _normalize_for_quote_match(quote)
    source_normalized = _normalize_for_quote_match(source)
    return bool(q) and q in source_normalized


def _check_citation(
    *,
    line: int | None,
    quote: str,
    field: str,
    turns_by_line: dict[int, list[TranscriptTurn]],
    issues: list[str],
    expected_speaker: str | None = None,
    quote_optional: bool = False,
) -> None:
    if line is None:
        if quote:
            issues.append(f"{field}: quote supplied without an evidence line")
        return

    seen_ids: set[str] = set()
    matching_turns: list[TranscriptTurn] = []
    for t in turns_by_line.get(line, []):
        if t.turn_id not in seen_ids:
            seen_ids.add(t.turn_id)
            matching_turns.append(t)
    if not matching_turns:
        issues.append(f"{field}: evidence line {line} does not exist")
        return
    if len(matching_turns) != 1:
        issues.append(f"{field}: evidence line {line} is ambiguous")
        return

    turn = matching_turns[0]
    if expected_speaker is not None and turn.speaker != expected_speaker:
        issues.append(
            f"{field}: evidence line {line} must be from a {expected_speaker} turn"
        )
    if quote_optional and not quote:
        return
    if not quote:
        issues.append(f"{field}: evidence quote is missing")
    elif quote not in turn.raw_text and (
        not turn.playback_heard_text or quote not in turn.playback_heard_text
    ):
        sources = [turn.raw_text or "", turn.playback_heard_text or ""]
        if not any(_normalized_contains(quote, source) for source in sources):
            issues.append(
                f"{field}: quote is not an exact substring of evidence line {line}"
            )


def _iter_quality_citations(
    result: ConversationQualityResult,
) -> Iterable[tuple[str, int | None, str, str | None, bool]]:
    for name, dimension in result.conversation_quality.dimensions:
        yield (
            f"conversation_quality.dimensions.{name}",
            dimension.evidence_line,
            dimension.quote,
            None,
            False,
        )

    for index, issue in enumerate(result.context_awareness.issues):
        prefix = f"context_awareness.issues[{index}]"
        yield (
            f"{prefix}.customer_evidence",
            issue.customer_evidence_line,
            issue.customer_quote,
            "customer",
            False,
        )
        yield (
            f"{prefix}.agent_evidence",
            issue.agent_evidence_line,
            issue.agent_quote,
            "agent",
            False,
        )

    for name, stage in result.conversation_completeness.stages:
        yield (
            f"conversation_completeness.stages.{name}",
            stage.evidence_line,
            "",
            None,
            True,
        )

    ftw = getattr(result, "first_thing_wrong", None) or getattr(result, "first_thing_wrong_candidate", None)
    if ftw and ftw.line is not None and str(ftw.category).upper() not in ("NONE", "UNKNOWN"):
        yield (
            "first_thing_wrong",
            ftw.line,
            ftw.quote,
            None,
            True,
        )
        for eline in getattr(ftw, "evidence_lines", []) or []:
            yield (
                "first_thing_wrong.evidence_lines",
                eline,
                "",
                None,
                True,
            )

    if result.what_happened:
        for line in result.what_happened.evidence_lines:
            yield (
                "what_happened",
                line,
                "",
                None,
                True,
            )


def _validate_result_evidence(
    batch_name: str,
    result: BaseModel,
    turns: list[TranscriptTurn],
    issues: list[str],
    sensitive_data: list[bool],
) -> None:
    turns_by_line: dict[int, list[TranscriptTurn]] = {}
    is_zero_based = bool(turns and turns[0].turn_index == 0)
    for turn in turns:
        line_num = (turn.turn_index + 1) if is_zero_based else turn.turn_index
        turns_by_line.setdefault(line_num, []).append(turn)

    def check(
        field: str,
        line: int | None,
        quote: str,
        expected_speaker: str | None = None,
        quote_optional: bool = False,
    ) -> None:
        _check_citation(
            line=line,
            quote=quote,
            field=field,
            turns_by_line=turns_by_line,
            issues=issues,
            expected_speaker=expected_speaker,
            quote_optional=quote_optional,
        )

    if batch_name == "conversation_understanding":
        understanding = result
        assert isinstance(understanding, ConversationUnderstandingResult)
        check(
            "outcome",
            understanding.outcome.evidence_line,
            understanding.outcome.quote,
        )
        check(
            "sentiment",
            understanding.sentiment.evidence_line,
            understanding.sentiment.quote,
            "customer",
        )
        check(
            "emotion",
            understanding.emotion.evidence_line,
            understanding.emotion.quote,
            "customer",
        )
        for index, fact in enumerate(understanding.customer_facts):
            if _contains_sensitive_customer_identifier(fact):
                sensitive_data.append(True)
                issues.append(
                    f"customer_facts[{index}]: contains a prohibited sensitive identifier"
                )
            check(
                f"customer_facts[{index}]",
                fact.evidence_line,
                fact.quote,
                "customer",
            )
        return

    if batch_name == "conversation_quality":
        quality = result
        assert isinstance(quality, ConversationQualityResult)
        for name, dimension in quality.conversation_quality.dimensions:
            if dimension.score is not None and dimension.evidence_line is None:
                issues.append(
                    f"conversation_quality.dimensions.{name}: "
                    "a non-null score requires transcript evidence"
                )
        for field, line, quote, speaker, quote_optional in _iter_quality_citations(
            quality
        ):
            check(field, line, quote, speaker, quote_optional)
        return

    if batch_name == "compliance_appointment":
        compliance = result
        assert isinstance(compliance, ComplianceAppointmentResult)
        for rule_name, rule in compliance.compliance.rule_results:
            check(
                f"compliance.rule_results.{rule_name}",
                rule.evidence_line,
                rule.quote,
                quote_optional=True,
            )
        for index, violation in enumerate(compliance.compliance.potential_violations):
            check(
                f"compliance.potential_violations[{index}]",
                violation.evidence_line,
                violation.quote,
            )
        appointment = compliance.appointment_interpretation
        if appointment.consent_status == "EXPLICIT":
            if (
                appointment.consent_evidence_line is None
                or not appointment.consent_quote.strip()
            ):
                issues.append(
                    "appointment_interpretation.consent: "
                    "explicit consent requires customer evidence"
                )
            elif is_unqualified_acknowledgement(appointment.consent_quote):
                issues.append(
                    "appointment_interpretation.consent: "
                    "an unqualified acknowledgement cannot establish explicit consent"
                )
        check(
            "appointment_interpretation.consent",
            appointment.consent_evidence_line,
            appointment.consent_quote,
            "customer",
        )
        check(
            "appointment_interpretation.agent_proposal",
            appointment.agent_proposal_line,
            appointment.agent_proposal_quote,
            "agent",
        )


def validate_batch_evidence(
    batch_name: str,
    result: BaseModel,
    turns: list[TranscriptTurn],
) -> ValidationReport:
    expected_model = _BATCH_MODELS.get(batch_name)
    if expected_model is None:
        issues = [f"Unknown evaluation batch: {batch_name}"]
        return ValidationReport(False, False, issues, issues.copy())

    if not isinstance(result, expected_model):
        issues = [
            f"Batch {batch_name} requires {expected_model.__name__}, "
            f"received {type(result).__name__}"
        ]
        return ValidationReport(False, False, issues, issues.copy())

    issues: list[str] = []
    if not turns:
        issues.append("Transcript is empty; evidence cannot be validated.")
    sensitive_data: list[bool] = []
    _validate_result_evidence(batch_name, result, turns, issues, sensitive_data)
    return ValidationReport(
        schema_valid=True,
        evidence_valid=not issues,
        issues=issues,
        review_reasons=issues.copy(),
        sensitive_data_detected=bool(sensitive_data),
    )
