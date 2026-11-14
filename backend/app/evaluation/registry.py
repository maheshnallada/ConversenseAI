import asyncio
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import uuid4

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
    ComplianceAppointmentResult,
    ConversationQualityResult,
    ConversationUnderstandingResult,
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
        return "\n".join(
            f"{turn.speaker.upper()} [Line {turn.turn_index}]: {turn.raw_text}"
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

    def _messages(
        self,
        batch_name: str,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
    ) -> list[dict[str, str]]:
        transcript = self._transcript_text(turns)
        if batch_name == "conversation_understanding":
            user_content = f"Evaluate this call.\nTRANSCRIPT:\n{transcript}"
        elif batch_name == "conversation_quality":
            user_content = (
                f"Evaluate the following.\nTRANSCRIPT:\n{transcript}\n"
                f"CALL METADATA (may be empty): "
                f"{json.dumps(interaction.domain_data or {}, ensure_ascii=False)}"
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

    async def _evaluate_batch(
        self,
        batch_name: str,
        response_model: type,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
    ) -> EvaluationBatchRecord:
        started_at = datetime.now(timezone.utc)
        try:
            completion = None
            for attempt in range(2):
                try:
                    completion = await self.structured_caller(
                        self._messages(batch_name, interaction, turns),
                        response_model,
                    )
                    break
                except LLMRequestError as error:
                    if not error.retryable or attempt == 1:
                        raise
                    await asyncio.sleep(0.1 * (attempt + 1))

            if isinstance(completion, StructuredCompletion):
                result = completion.result
                raw_output = completion.raw_output
                input_tokens = completion.input_tokens
                output_tokens = completion.output_tokens
            else:
                result = completion
                raw_output = None
                input_tokens = None
                output_tokens = None

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
                input_tokens=input_tokens,
                output_tokens=output_tokens,
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
