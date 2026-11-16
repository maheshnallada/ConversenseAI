import asyncio
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

    def evaluate_interaction(
        self,
        tenant_id: str,
        interaction_id: str,
        retry_from_run_id: str | None = None,
    ) -> EvaluationRun:
        """
        Loads an existing interaction and its context, runs the evaluation batches,
        persists the versioned run, and returns it.
        """
        envelope = self._load_envelope(tenant_id, interaction_id)
        if not envelope:
            raise ValueError(f"Interaction {tenant_id}:{interaction_id} not found in database.")

        turns = self.transcript_repo.get_turns(tenant_id, interaction_id)
        timeline = self.timeline_repo.get_timeline(tenant_id, interaction_id)
        return asyncio.run(
            self._evaluate_context(
                envelope,
                turns,
                evaluation_namespace="interaction",
                timeline=timeline,
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
                if batch.status == "failed"
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
                if batch.batch_name not in evaluated_names and batch.status != "failed"
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
            if batch.status == "completed" and batch.parsed_output is not None
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
            "first_thing_wrong_line": summary.first_thing_wrong_line,
            "first_thing_wrong_what": summary.first_thing_wrong_what,
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
        booking_event = next(
            (
                event.model_dump(mode="python")
                for event in envelope.events or []
                if event.event_type in {"appointment.booked", "booking.confirmed"}
            ),
            None,
        )
        rules_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "configs"
            / "evaluators"
            / "health_insurance_rules.json"
        )
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
