from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel

from app.domain.transcript import TranscriptTurn
from app.evaluation.schemas import (
    ComplianceAppointmentResult,
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

    matching_turns = turns_by_line.get(line)
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
    elif quote not in turn.raw_text:
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


def _validate_result_evidence(
    batch_name: str,
    result: BaseModel,
    turns: list[TranscriptTurn],
    issues: list[str],
) -> None:
    turns_by_line: dict[int, list[TranscriptTurn]] = {}
    for turn in turns:
        turns_by_line.setdefault(turn.turn_index, []).append(turn)

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
    _validate_result_evidence(batch_name, result, turns, issues)
    return ValidationReport(
        schema_valid=True,
        evidence_valid=not issues,
        issues=issues,
        review_reasons=issues.copy(),
    )
