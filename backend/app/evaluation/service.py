import asyncio, os
import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.timeline import ReconstructedTimeline
from app.domain.transcript import TranscriptTurn
from app.evaluation.derivation import (
    AppointmentValidation,
    derive_appointment_validity,
    derive_evaluation_summary,
)
from app.evaluation.registry import EvaluatorRegistry
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.transcript_repo import TranscriptRepository
from app.storage.timeline_repo import TimelineRepository
from app.storage.orm import InteractionRow


def _find_rules_path() -> Path:
    env_path = os.getenv("RULES_CONFIG_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    candidates = [
        Path("/app/configs/evaluators/health_insurance_rules.json"),
        Path(__file__).resolve().parent.parent.parent.parent / "configs" / "evaluators" / "health_insurance_rules.json",
        Path(__file__).resolve().parent.parent.parent / "configs" / "evaluators" / "health_insurance_rules.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[1]


class EvaluationService:
    def __init__(
        self,
        session_factory: sessionmaker,
        registry: Optional[EvaluatorRegistry] = None,
    ):
        self.session_factory = session_factory
        self.registry = registry or EvaluatorRegistry()
        self.eval_repo = EvaluationRepository(session_factory)
        self.transcript_repo = TranscriptRepository(session_factory)
        self.timeline_repo = TimelineRepository(session_factory)

    async def evaluate_input(
        self,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        evaluation_namespace: str = "interaction",
        timeline: ReconstructedTimeline | None = None,
    ) -> EvaluationRun:
        """
        Evaluates a supplied interaction envelope and transcript without loading a
        persisted interaction record. The run and its batches are scoped to the
        requested evaluation namespace.
        """
        return await self._evaluate_context(
            interaction,
            turns,
            evaluation_namespace=evaluation_namespace,
            timeline=timeline,
        )

    async def evaluate_interaction_async(
        self,
        tenant_id: str,
        interaction_id: str,
        retry_from_run_id: str | None = None,
    ) -> EvaluationRun:
        """
        Asynchronously loads an interaction context, runs evaluation batches concurrently,
        persists the run, and returns it.
        """
        envelope = await asyncio.to_thread(self._load_envelope, tenant_id, interaction_id)
        if not envelope:
            raise ValueError(f"Interaction {tenant_id}:{interaction_id} not found in database.")

        turns = await asyncio.to_thread(self.transcript_repo.get_turns, tenant_id, interaction_id)
        timeline = await asyncio.to_thread(self.timeline_repo.get_timeline, tenant_id, interaction_id)
        return await self._evaluate_context(
            envelope,
            turns,
            evaluation_namespace="interaction",
            timeline=timeline,
            retry_from_run_id=retry_from_run_id,
        )

    def evaluate_interaction(
        self,
        tenant_id: str,
        interaction_id: str,
        retry_from_run_id: str | None = None,
    ) -> EvaluationRun:
        """
        Synchronous wrapper for evaluate_interaction_async.
        """
        return asyncio.run(
            self.evaluate_interaction_async(
                tenant_id,
                interaction_id,
                retry_from_run_id=retry_from_run_id,
            )
        )

    async def _evaluate_context(
        self,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        evaluation_namespace: str,
        timeline: ReconstructedTimeline | None = None,
        retry_from_run_id: str | None = None,
    ) -> EvaluationRun:
        previous_run = None
        retry_batches: set[str] | None = None
        if retry_from_run_id is not None:
            previous_run = self.eval_repo.get_run(
                interaction.tenant_id,
                interaction.interaction_id,
                retry_from_run_id,
                evaluation_namespace=evaluation_namespace,
            )
            if previous_run is None:
                raise ValueError(
                    f"Evaluation run {retry_from_run_id} was not found for "
                    f"{interaction.tenant_id}:{interaction.interaction_id}."
                )
            retry_batches = {
                batch.batch_name
                for batch in previous_run.batches
                if batch.status in {"failed", "review_required"}
            }

        evaluated_run = await self.registry.evaluate_batches(
            interaction=interaction,
            turns=turns,
            timeline=timeline,
            batch_names=retry_batches,
        )
        if previous_run is not None:
            evaluated_names = {batch.batch_name for batch in evaluated_run.batches}
            carried_forward = [
                replace(
                    copy.deepcopy(batch),
                    evaluation_id=str(uuid4()),
                    source_evaluation_id=batch.evaluation_id,
                )
                for batch in previous_run.batches
                if batch.batch_name not in evaluated_names
                and batch.status not in {"failed", "review_required"}
            ]
            evaluated_run.batches = carried_forward + evaluated_run.batches

        evaluated_run.evaluation_namespace = evaluation_namespace
        for batch in evaluated_run.batches:
            batch.evaluation_namespace = evaluation_namespace

        appointment_validation = self._derive_appointment_validation(
            interaction,
            evaluated_run.batches,
        )
        available_results = {
            batch.batch_name: batch.parsed_output
            for batch in evaluated_run.batches
            if batch.status in {"completed", "review_required"}
            and batch.parsed_output is not None
        }
        summary = derive_evaluation_summary(
            available_results,
            timeline,
            appointment_validation,
        )
        evaluated_run.summary = {
            "overall_assessment": summary.overall_assessment,
            "dimension_assessments": summary.dimension_assessments,
            "first_failure": {
                "status": summary.first_failure.status,
                "first_failure": (
                    summary.first_failure.first_failure.__dict__
                    if summary.first_failure.first_failure
                    else None
                ),
                "critical_failures": [
                    failure.__dict__
                    for failure in summary.first_failure.critical_failures
                ],
            },
            "critical_issues": summary.critical_issues,
            "requires_human_review": summary.requires_human_review,
            "review_reasons": summary.review_reasons,
            "what_happened": summary.what_happened,
            "first_thing_wrong_category": summary.first_thing_wrong_category,
            "first_thing_wrong_line": summary.first_thing_wrong_line,
            "first_thing_wrong_description": summary.first_thing_wrong_description,
            "first_thing_wrong_what": summary.first_thing_wrong_what,
            "technical_failure_category": summary.technical_failure_category,
            "conversational_failure_category": summary.conversational_failure_category,
            "compliance_failure_category": summary.compliance_failure_category,
            "appointment_validation": (
                appointment_validation.__dict__ if appointment_validation else None
            ),
        }
        evaluated_run.review_reasons = list(dict.fromkeys(
            [
                *evaluated_run.review_reasons,
                *summary.review_reasons,
                *(
                    [appointment_validation.reason]
                    if appointment_validation
                    and appointment_validation.status == "NOT_EVALUABLE"
                    else []
                ),
            ]
        ))
        evaluated_run.review_required = (
            evaluated_run.review_required
            or summary.requires_human_review
            or any(batch.review_required for batch in evaluated_run.batches)
        )
        self.eval_repo.save_run(evaluated_run)
        return evaluated_run

    def _derive_appointment_validation(
        self,
        envelope: InteractionEnvelope,
        batches: list[EvaluationBatchRecord],
    ) -> AppointmentValidation | None:
        compliance_batch = next(
            (
                batch
                for batch in batches
                if batch.batch_name == "compliance_appointment"
                and batch.status == "completed"
                and not batch.review_required
                and batch.validation.get("schema_valid") is True
                and batch.validation.get("evidence_valid") is True
                and batch.parsed_output is not None
            ),
            None,
        )
        if compliance_batch is None:
            return None

        from app.evaluation.schemas import ComplianceAppointmentResult

        result = ComplianceAppointmentResult.model_validate(
            compliance_batch.parsed_output
        )
        domain_data = envelope.domain_data or {}
        meta = domain_data.get("meta") if isinstance(domain_data, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        timezone_name = (
            domain_data.get("timezone")
            if isinstance(domain_data, dict)
            else None
        ) or meta.get("timezone")

        if not timezone_name or timezone_name == "unknown":
            if envelope.started_at and envelope.started_at.tzinfo:
                tz_str = str(envelope.started_at.tzinfo)
                if "+05:30" in tz_str or "UTC+05:30" in tz_str:
                    timezone_name = "Asia/Kolkata"
                else:
                    timezone_name = tz_str
            else:
                timezone_name = "Asia/Kolkata"

        booking_event = next(
            (
                event.model_dump(mode="python")
                for event in envelope.events or []
                if event.event_type in {"appointment.booked", "booking.confirmed"}
            ),
            None,
        )

        if booking_event is None:
            end_call = meta.get("end_call") or domain_data.get("end_call")
            if isinstance(end_call, dict):
                outcome = str(end_call.get("outcome") or "").strip().upper()
                rec = (
                    end_call.get("record")
                    if isinstance(end_call.get("record"), dict)
                    else {}
                )
                expert_call_at = (
                    rec.get("expert_call_at")
                    or end_call.get("expert_call_at")
                    or rec.get("appointment_at")
                    or end_call.get("appointment_at")
                )
                call_later_at = rec.get("call_later_at") or end_call.get("call_later_at")

                occurred_at = (
                    envelope.ended_at.isoformat()
                    if envelope.ended_at
                    else (
                        envelope.started_at.isoformat()
                        if envelope.started_at
                        else None
                    )
                )

                if outcome == "APPOINTMENT_BOOKED" and expert_call_at:
                    booking_event = {
                        "event_id": f"{envelope.interaction_id}_booking",
                        "event_type": "appointment.booked",
                        "occurred_at": occurred_at,
                        "payload": {
                            "appointment_at": expert_call_at,
                            "outcome": outcome,
                            "commitments": end_call.get("commitments", []),
                            "summary": end_call.get("summary"),
                            "closing_line": end_call.get("closing_line"),
                            "record": rec,
                        },
                    }
                elif outcome in {"CALLBACK_BOOKED", "CALL_LATER"} or call_later_at:
                    booking_event = {
                        "event_id": f"{envelope.interaction_id}_callback",
                        "event_type": "callback.scheduled",
                        "occurred_at": occurred_at,
                        "payload": {
                            "callback_at": call_later_at,
                            "outcome": outcome or "CALL_LATER",
                            "commitments": end_call.get("commitments", []),
                            "summary": end_call.get("summary"),
                            "closing_line": end_call.get("closing_line"),
                            "record": rec,
                        },
                    }
        rules_path = _find_rules_path()
        with rules_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        never_rules = config.get("never_rules")
        if not isinstance(never_rules, dict):
            raise ValueError("Health-insurance appointment policy is unavailable.")
        return derive_appointment_validity(
            result.appointment_interpretation,
            booking_event,
            envelope.started_at,
            timezone_name,
            never_rules,
        )

    def _load_envelope(self, tenant_id: str, interaction_id: str) -> Optional[InteractionEnvelope]:
        with self.session_factory() as session:
            row = session.scalar(
                select(InteractionRow).where(
                    InteractionRow.tenant_id == tenant_id,
                    InteractionRow.interaction_id == interaction_id,
                )
            )
            if not row:
                return None

            return InteractionEnvelope.model_validate_json(row.payload_json)
