import asyncio
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import uuid4

from openai import BaseModel

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.evaluation.derivation import derive_evaluation_summary
from app.evaluation.errors import LLMError, LLMRequestError, LLMResponseError
from app.evaluation.evidence import validate_batch_evidence
from app.evaluation.llm_client import (
    LLMClient,
    StructuredCompletion,
    complete_structured_with_usage,
)
from app.evaluation.prompts import BATCH_SYSTEM_PROMPTS
from app.evaluation.schemas import (
    AppointmentInterpretation,
    Compliance,
    ComplianceAppointmentResult,
    ComplianceRuleResult,
    ComplianceRules,
    CompletenessStage,
    CompletenessStages,
    ContextAwareness,
    ContextAwarenessDimensions,
    ConversationCompleteness,
    ConversationQuality,
    ConversationQualityResult,
    ConversationUnderstandingResult,
    EmotionResult,
    FirstThingWrongCandidate,
    OutcomeResult,
    QualityDimension,
    QualityDimensions,
    SentimentResult,
    WhatHappenedResult,
)

logger = logging.getLogger(__name__)


_BATCH_MODELS = {
    "conversation_understanding": ConversationUnderstandingResult,
    "conversation_quality": ConversationQualityResult,
    "compliance_appointment": ComplianceAppointmentResult,
}
_PROMPT_VERSION = "1.0.0"
_SCHEMA_VERSION = "1.0.0"


class EvaluatorRegistry:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        structured_caller=None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.structured_caller = structured_caller or complete_structured_with_usage

    @staticmethod
    def _transcript_text(turns: list[TranscriptTurn]) -> str:
        is_zero_based = bool(turns and turns[0].turn_index == 0)
        return "\n".join(
            f"{turn.speaker.upper()} [Line {(turn.turn_index + 1) if is_zero_based else turn.turn_index}]: {turn.raw_text}"
            for turn in turns
        )

    @staticmethod
    def _booking_context(interaction: InteractionEnvelope) -> tuple[str, str, str]:
        call_date = (
            interaction.started_at.date().isoformat()
            if interaction.started_at
            else "unknown"
        )
        domain_data = interaction.domain_data or {}
        meta = domain_data.get("meta") if isinstance(domain_data, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        timezone_name = (
            domain_data.get("timezone")
            if isinstance(domain_data, dict)
            else None
        ) or meta.get("timezone") or "unknown"
        booking_event = next(
            (
                event.model_dump(mode="json")
                for event in interaction.events or []
                if event.event_type in {"appointment.booked", "booking.confirmed"}
            ),
            None,
        )
        return call_date, timezone_name, json.dumps(booking_event, ensure_ascii=False)

    @staticmethod
    def _build_batch_two_payload(
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        timeline: ReconstructedTimeline | None = None,
    ) -> dict[str, Any]:
        call_data = interaction.domain_data or {}
        meta = call_data.get("meta") if isinstance(call_data.get("meta"), dict) else {}
        call_timing_meta = (
            call_data.get("call_timing")
            if isinstance(call_data.get("call_timing"), dict)
            else {}
        )

        call_id = (
            call_data.get("folder_name")
            or call_data.get("call_id")
            or interaction.interaction_id
        )

        answered_at_s = call_timing_meta.get("answered_at_seconds")
        if answered_at_s is None:
            if turns and turns[0].start_s is not None:
                answered_at_s = round(turns[0].start_s, 3)
            elif timeline and timeline.first_agent_speech_s is not None:
                answered_at_s = round(timeline.first_agent_speech_s, 3)
            elif "ring_s" in meta and meta["ring_s"] is not None:
                try:
                    answered_at_s = round(float(meta["ring_s"]), 3)
                except (ValueError, TypeError):
                    pass

        ended_at_s = call_timing_meta.get("ended_at_seconds")
        if ended_at_s is None:
            line_usage = (
                meta.get("usage", {}).get("line", {})
                if isinstance(meta.get("usage"), dict)
                else {}
            )
            if line_usage.get("connected_s") is not None:
                try:
                    ended_at_s = round(float(line_usage["connected_s"]), 3)
                except (ValueError, TypeError):
                    pass
            elif interaction.started_at and interaction.ended_at:
                ended_at_s = round(
                    (interaction.ended_at - interaction.started_at).total_seconds(), 3
                )
            elif turns and any(t.end_s is not None for t in turns):
                ended_at_s = max(t.end_s for t in turns if t.end_s is not None)
            elif timeline and timeline.total_duration_s is not None:
                ended_at_s = round(timeline.total_duration_s, 3)

        duration_s = call_timing_meta.get("duration_seconds")
        if duration_s is None:
            if (
                ended_at_s is not None
                and answered_at_s is not None
                and ended_at_s >= answered_at_s
            ):
                duration_s = round(ended_at_s - answered_at_s, 3)
            elif timeline and timeline.total_duration_s is not None:
                duration_s = round(timeline.total_duration_s, 3)
            elif ended_at_s is not None:
                duration_s = ended_at_s

        end_reason = (
            call_timing_meta.get("end_reason")
            or call_data.get("end_reason")
            or meta.get("end_reason")
            or (meta.get("end_call") or {}).get("outcome")
            or call_data.get("disposition")
        )
        if end_reason == "dropped":
            end_reason = "call_dropped"

        events: list[dict[str, Any]] = []
        for idx, t in enumerate(turns, start=1):
            line_num = idx
            speaker = t.speaker.lower() if t.speaker else "unknown"
            if speaker == "agent":
                status = t.playback_spoken or "heard"
                heard_text = None if status == "heard" else t.playback_heard_text
                barged_in = (
                    bool(t.barged_in)
                    if t.barged_in is not None
                    else (status == "cut")
                )
                events.append(
                    {
                        "line": line_num,
                        "speaker": "agent",
                        "timestamp_seconds": t.start_s,
                        "duration_seconds": t.duration_s or t.audio_s,
                        "generated_text": t.raw_text,
                        "playback_status": status,
                        "heard_text": heard_text,
                        "barged_in": barged_in,
                    }
                )
            else:
                events.append(
                    {
                        "line": line_num,
                        "speaker": speaker,
                        "timestamp_seconds": t.start_s,
                        "text": t.raw_text,
                    }
                )

        return {
            "call_id": call_id,
            "call_timing": {
                "answered_at_seconds": answered_at_s,
                "ended_at_seconds": ended_at_s,
                "duration_seconds": duration_s,
                "end_reason": end_reason,
            },
            "events": events,
        }

    def _messages(
        self,
        batch_name: str,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        timeline: ReconstructedTimeline | None = None,
    ) -> list[dict[str, str]]:
        transcript = self._transcript_text(turns)
        if batch_name == "conversation_understanding":
            user_content = f"Evaluate this call.\nTRANSCRIPT:\n{transcript}"
        elif batch_name == "conversation_quality":
            payload = self._build_batch_two_payload(interaction, turns, timeline)
            user_content = (
                f"Evaluate the following call events, timing, and playback details:\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            )
        else:
            call_date, timezone_name, booking_event = self._booking_context(interaction)
            user_content = (
                f"CALL DATE: {call_date}\nTIMEZONE: {timezone_name}\n"
                f"BOOKING EVENT (may be null): {booking_event}\n"
                f"TRANSCRIPT:\n{transcript}"
            )
        return [
            {"role": "system", "content": BATCH_SYSTEM_PROMPTS[batch_name]},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _is_not_answered(interaction: InteractionEnvelope) -> bool:
        call_data = interaction.domain_data or {}
        meta = call_data.get("meta") if isinstance(call_data.get("meta"), dict) else {}
        call_timing_meta = (
            call_data.get("call_timing")
            if isinstance(call_data.get("call_timing"), dict)
            else {}
        )
        end_reason = (
            call_timing_meta.get("end_reason")
            or call_data.get("end_reason")
            or meta.get("end_reason")
            or (meta.get("end_call") or {}).get("outcome")
            or call_data.get("disposition")
        )
        if isinstance(end_reason, str):
            norm = end_reason.strip().lower().replace("-", "_").replace(" ", "_")
            if norm in {
                "not_answered",
                "no_answer",
                "unanswered",
                "missed",
                "customer_unreachable",
            }:
                return True
        return False

    @staticmethod
    def _build_deterministic_output(
        batch_name: str,
        interaction: InteractionEnvelope,
        reason_label: str = "Call was not answered.",
    ) -> BaseModel:
        if batch_name == "conversation_understanding":
            return ConversationUnderstandingResult(
                outcome=OutcomeResult(
                    label="Can't tell",
                    evidence_line=None,
                    quote="",
                    reason=reason_label,
                ),
                customer_facts=[],
                sentiment=SentimentResult(
                    label="Can't tell",
                    evidence_line=None,
                    quote="",
                    reason=reason_label,
                ),
                emotion=EmotionResult(
                    label="Can't tell",
                    evidence_line=None,
                    quote="",
                    reason=reason_label,
                ),
            )
        elif batch_name == "conversation_quality":
            dims = {
                d: QualityDimension(
                    score=None,
                    evidence_line=None,
                    quote="",
                    reason=reason_label,
                )
                for d in (
                    "clarity",
                    "relevance",
                    "empathy",
                    "professionalism",
                    "naturalness",
                    "responsiveness",
                    "closing_quality",
                )
            }
            stages = CompletenessStages(
                opening=CompletenessStage(status="not_observed", evidence_line=None),
                customer_engagement=CompletenessStage(
                    status="not_observed", evidence_line=None
                ),
                purpose_explanation=CompletenessStage(
                    status="not_observed", evidence_line=None
                ),
                information_collection=CompletenessStage(
                    status="not_observed", evidence_line=None
                ),
                outcome_establishment=CompletenessStage(
                    status="not_observed", evidence_line=None
                ),
                closing=CompletenessStage(status="not_observed", evidence_line=None),
            )
            return ConversationQualityResult(
                conversation_quality=ConversationQuality(
                    dimensions=QualityDimensions(**dims),
                    strengths=[],
                    improvement_areas=[],
                ),
                context_awareness=ContextAwareness(
                    issues=[],
                    dimensions=ContextAwarenessDimensions(
                        repeated_questions=False,
                        ignored_information=False,
                        contradictory_responses=False,
                        irrelevant_followups=False,
                        poor_objection_handling=False,
                    ),
                    score=None,
                    first_context_failure_line=None,
                ),
                conversation_completeness=ConversationCompleteness(
                    stages=stages,
                    conversation_status="NO_MEANINGFUL_INTERACTION",
                    customer_abandoned=None,
                    reason=reason_label,
                ),
                what_happened=WhatHappenedResult(
                    label="Can't tell",
                    evidence_lines=[],
                    reason=reason_label,
                    review_required=False,
                ),
                first_thing_wrong=FirstThingWrongCandidate(
                    category="NONE",
                    line=None,
                    quote="",
                    description=reason_label,
                    evidence_lines=[],
                    source="metadata",
                    review_required=False,
                ),
            )
        else:
            return ComplianceAppointmentResult(
                compliance=Compliance(
                    rule_results=ComplianceRules(
                        NR001=ComplianceRuleResult(
                            status="NOT_DETECTED",
                            reason=reason_label,
                            evidence_line=None,
                            quote="",
                        ),
                        NR002=ComplianceRuleResult(
                            status="NOT_DETECTED",
                            reason=reason_label,
                            evidence_line=None,
                            quote="",
                        ),
                        NR003=ComplianceRuleResult(
                            status="NOT_DETECTED",
                            reason=reason_label,
                            evidence_line=None,
                            quote="",
                        ),
                        NR004=ComplianceRuleResult(
                            status="NOT_DETECTED",
                            reason=reason_label,
                            evidence_line=None,
                            quote="",
                        ),
                        NR005=ComplianceRuleResult(
                            status="NOT_DETECTED",
                            reason=reason_label,
                            evidence_line=None,
                            quote="",
                        ),
                        NR006=ComplianceRuleResult(
                            status="NOT_DETECTED",
                            reason=reason_label,
                            evidence_line=None,
                            quote="",
                        ),
                    ),
                    potential_violations=[],
                ),
                appointment_interpretation=AppointmentInterpretation(
                    appointment_type="NONE",
                    consent_status="NOT_PRESENT",
                    consent_evidence_line=None,
                    consent_quote="",
                    agent_proposal_line=None,
                    agent_proposal_quote="",
                    date_text=None,
                    time_text=None,
                    interpreted_date=None,
                    interpreted_time=None,
                    interpretation_reason=reason_label,
                ),
            )

    async def _evaluate_batch(
        self,
        batch_name: str,
        response_model: type,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        timeline: ReconstructedTimeline | None = None,
    ) -> EvaluationBatchRecord:
        started_at = datetime.now(timezone.utc)
        is_empty = not turns or not any(t.raw_text and t.raw_text.strip() for t in turns)
        is_unanswered = self._is_not_answered(interaction)

        if is_unanswered:
            completed_at = datetime.now(timezone.utc)
            deterministic_output = self._build_deterministic_output(
                batch_name, interaction, "Customer did not answer the call."
            )
            return EvaluationBatchRecord(
                evaluation_id=str(uuid4()),
                batch_name=batch_name,
                status="completed",
                model="deterministic",
                prompt_version=_PROMPT_VERSION,
                schema_version=_SCHEMA_VERSION,
                started_at=started_at,
                completed_at=completed_at,
                input_tokens=0,
                output_tokens=0,
                raw_output=deterministic_output.model_dump_json(),
                parsed_output=deterministic_output.model_dump(mode="json"),
                validation={
                    "schema_valid": True,
                    "evidence_valid": True,
                    "issues": [],
                    "review_reasons": [],
                    "sensitive_data_detected": False,
                },
                review_required=False,
                review_status="not_required",
                review_reasons=[],
            )

        if is_empty:
            completed_at = datetime.now(timezone.utc)
            issues = ["Transcript is empty; cannot evaluate interaction."]
            return EvaluationBatchRecord(
                evaluation_id=str(uuid4()),
                batch_name=batch_name,
                status="review_required",
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                prompt_version=_PROMPT_VERSION,
                schema_version=_SCHEMA_VERSION,
                started_at=started_at,
                completed_at=completed_at,
                input_tokens=None,
                output_tokens=None,
                raw_output=None,
                parsed_output=None,
                validation={
                    "schema_valid": True,
                    "evidence_valid": False,
                    "issues": issues,
                    "review_reasons": issues.copy(),
                    "sensitive_data_detected": False,
                },
                review_required=True,
                review_status="required",
                review_reasons=issues.copy(),
            )

        try:
            current_messages = self._messages(batch_name, interaction, turns, timeline)
            completion = None
            validation = None
            result = None
            raw_output = None
            total_input_tokens = 0
            total_output_tokens = 0
            tokens_tracked = False

            for eval_attempt in range(2):
                for req_attempt in range(2):
                    try:
                        completion = await self.structured_caller(
                            current_messages,
                            response_model,
                        )
                        break
                    except LLMRequestError as error:
                        if not error.retryable or req_attempt == 1:
                            raise
                        await asyncio.sleep(0.1 * (req_attempt + 1))

                if isinstance(completion, StructuredCompletion):
                    result = completion.result
                    raw_output = completion.raw_output
                    if completion.input_tokens is not None:
                        total_input_tokens += completion.input_tokens
                        tokens_tracked = True
                    if completion.output_tokens is not None:
                        total_output_tokens += completion.output_tokens
                        tokens_tracked = True
                else:
                    result = completion
                    raw_output = None

                if not isinstance(result, response_model):
                    raise LLMResponseError(
                        "Provider returned an unexpected structured result model",
                        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                        provider=os.getenv("LLM_PROVIDER", "unknown").lstrip("@"),
                    )

                validation = validate_batch_evidence(batch_name, result, turns)
                if validation.sensitive_data_detected:
                    raise LLMResponseError(
                        "Provider output contained a prohibited sensitive customer "
                        "identifier; batch output was discarded",
                        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                        provider=os.getenv("LLM_PROVIDER", "unknown").lstrip("@"),
                    )

                if validation.schema_valid and validation.evidence_valid:
                    break

                if eval_attempt == 0:
                    logger.warning(
                        "Batch %s validation failed on attempt 1 with issues: %s. Retrying with error context.",
                        batch_name,
                        validation.issues,
                    )
                    error_details = "\n".join(f"- {issue}" for issue in validation.issues)
                    assistant_content = (
                        raw_output
                        if raw_output
                        else (
                            result.model_dump_json()
                            if hasattr(result, "model_dump_json")
                            else str(result)
                        )
                    )
                    current_messages = list(current_messages) + [
                        {"role": "assistant", "content": assistant_content},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response had the following structured output validation error(s):\n"
                                f"{error_details}\n\n"
                                "Please regenerate the entire JSON response adhering strictly to the schema. "
                                "Ensure that all cited evidence line numbers exist in the transcript and all quotes are verbatim substrings from the cited line."
                            ),
                        },
                    ]
                    continue

            review_required = not (
                validation.schema_valid and validation.evidence_valid
            )
            completed_at = datetime.now(timezone.utc)
            result_data = result.model_dump(mode="json") if turns else None
            return EvaluationBatchRecord(
                evaluation_id=str(uuid4()),
                batch_name=batch_name,
                status="review_required" if review_required else "completed",
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                prompt_version=_PROMPT_VERSION,
                schema_version=_SCHEMA_VERSION,
                started_at=started_at,
                completed_at=completed_at,
                input_tokens=total_input_tokens if tokens_tracked else None,
                output_tokens=total_output_tokens if tokens_tracked else None,
                raw_output=(
                    (raw_output or result.model_dump_json()) if turns else None
                ),
                parsed_output=result_data,
                validation=asdict(validation),
                review_required=review_required,
                review_status="required" if review_required else "not_required",
                review_reasons=validation.review_reasons,
            )
        except LLMError as error:
            completed_at = datetime.now(timezone.utc)
            return EvaluationBatchRecord(
                evaluation_id=str(uuid4()),
                batch_name=batch_name,
                status="failed",
                model=error.model,
                prompt_version=_PROMPT_VERSION,
                schema_version=_SCHEMA_VERSION,
                started_at=started_at,
                completed_at=completed_at,
                input_tokens=None,
                output_tokens=None,
                raw_output=None,
                parsed_output=None,
                validation={
                    "schema_valid": False,
                    "evidence_valid": False,
                    "issues": [str(error)],
                },
                review_required=True,
                review_status="required",
                review_reasons=[str(error)],
                error_type=type(error).__name__,
                error_message=str(error),
            )

    async def evaluate_batches(
        self,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        timeline: ReconstructedTimeline | None = None,
        batch_names: set[str] | None = None,
    ) -> EvaluationRun:
        selected_names = set(_BATCH_MODELS) if batch_names is None else batch_names
        unknown_names = selected_names - set(_BATCH_MODELS)
        if unknown_names:
            raise ValueError(f"Unknown evaluation batches: {sorted(unknown_names)}")

        started_at = datetime.now(timezone.utc)
        results = await asyncio.gather(
            *(
                self._evaluate_batch(
                    batch_name,
                    _BATCH_MODELS[batch_name],
                    interaction,
                    turns,
                    timeline,
                )
                for batch_name in _BATCH_MODELS
                if batch_name in selected_names
            )
        )
        successful_results = {
            batch.batch_name: batch.parsed_output
            for batch in results
            if batch.status == "completed" and batch.parsed_output is not None
        }
        summary = derive_evaluation_summary(
            successful_results,
            timeline,
            appointment_validation=None,
        )
        summary_data = asdict(summary)
        review_reasons = list(summary.review_reasons)
        for batch in results:
            review_reasons.extend(
                reason
                for reason in batch.review_reasons
                if reason not in review_reasons
            )
        return EvaluationRun(
            run_id=str(uuid4()),
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.interaction_id,
            batches=results,
            summary=summary_data,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            review_required=summary.requires_human_review
            or any(batch.review_required for batch in results),
            review_reasons=review_reasons,
        )
