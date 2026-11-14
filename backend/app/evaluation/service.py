import asyncio
import copy
import json
import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationBatchRecord, EvaluationResult, EvaluationRun
from app.evaluation.derivation import (
    AppointmentValidation,
    derive_appointment_validity,
    derive_evaluation_summary,
)
from app.evaluation.registry import EvaluatorRegistry
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.transcript_repo import TranscriptRepository
from app.storage.timeline_repo import TimelineRepository
from app.storage.observability_repo import ObservabilityRepository
from app.storage.orm import InteractionRow, ArtifactRow, OutboxRow
from app.storage.artifacts import LocalArtifactStore
from app.ingestion.mapper import map_call_folder
from app.ingestion.service import ACCEPTED_EVENT, canonical_json, payload_hash
from app.reconstruction.processor import TranscriptProcessor
from app.reconstruction.reconstructor import TimelineReconstructor
from app.observability.service import ObservabilityService
from app.observability.config import RateCardManager

logger = logging.getLogger(__name__)


class EvaluationService:
    def __init__(
        self,
        session_factory: sessionmaker,
        registry: Optional[EvaluatorRegistry] = None,
        artifact_store: Optional[LocalArtifactStore] = None,
        rate_card_manager: Optional[RateCardManager] = None,
        trusted_call_roots: list[Path | str] | None = None,
    ):
        self.session_factory = session_factory
        self.registry = registry or EvaluatorRegistry()
        self.eval_repo = EvaluationRepository(session_factory)
        self.transcript_repo = TranscriptRepository(session_factory)
        self.timeline_repo = TimelineRepository(session_factory)
        self.obs_repo = ObservabilityRepository(session_factory)

        root = Path(__file__).resolve().parent.parent.parent.parent
        artifact_root = (
            os.getenv("ARTIFACT_STORAGE_PATH")
            or os.getenv("ARTIFACT_STORE_PATH")
            or os.getenv("ARTIFACTS_DIR")
            or root / "backend" / "storage" / "artifacts"
        )
        self.artifact_store = artifact_store or LocalArtifactStore(artifact_root)
        self.rate_card_manager = rate_card_manager or RateCardManager(root / "configs" / "rate_cards.json")
        self.trusted_call_roots = [
            Path(path).resolve() for path in (trusted_call_roots or [])
        ]
        self.obs_service = ObservabilityService(session_factory, self.rate_card_manager)
        self.processor = TranscriptProcessor()
        self.reconstructor = TimelineReconstructor()

    def resolve_interaction_id(self, tenant_id: str, identifier: str) -> str:
        """
        Resolves identifier which might be a call folder name ('call_01')
        or a UUID interaction_id.
        """
        with self.session_factory() as session:
            direct = session.scalar(
                select(InteractionRow).where(
                    InteractionRow.tenant_id == tenant_id,
                    InteractionRow.interaction_id == identifier,
                )
            )
            if direct:
                return direct.interaction_id

        if identifier.startswith("call_"):
            artifact_root = self.artifact_store.base_dir.resolve()
            tenant_root = (artifact_root / tenant_id).resolve()
            call_json = (tenant_root / identifier / "call.json").resolve()
            if tenant_root.is_relative_to(artifact_root) and call_json.is_relative_to(tenant_root):
                if call_json.exists():
                    with open(call_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    call_id = data.get("call_id") if isinstance(data, dict) else None
                    if isinstance(call_id, str) and call_id:
                        return call_id

        return identifier

    def _find_call_folder(
        self, call_folder_path: Path | str, tenant_id: str | None = None
    ) -> Path:
        raw_path = Path(str(call_folder_path).strip())
        effective_tenant = tenant_id or os.getenv("TENANT_ID", "health_campaign")
        root = Path(__file__).resolve().parent.parent.parent.parent
        artifact_root = self.artifact_store.base_dir.resolve()
        tenant_artifact_root = (artifact_root / effective_tenant).resolve()
        uploads_root = (root / "backend" / "storage" / "uploads" / effective_tenant).resolve()
        candidate_roots = [
            (root / "data" / "calls").resolve(),
            uploads_root,
            tenant_artifact_root,
            Path("/app/data/calls").resolve(),
            *self.trusted_call_roots,
        ]

        if not tenant_artifact_root.is_relative_to(artifact_root):
            raise FileNotFoundError(f"Call folder not found: '{call_folder_path}'")
        if not uploads_root.is_relative_to((root / "backend" / "storage" / "uploads").resolve()):
            raise FileNotFoundError(f"Call folder not found: '{call_folder_path}'")

        for candidate_root in candidate_roots:
            if not candidate_root.is_dir():
                continue
            candidates = [raw_path] if raw_path.is_absolute() else [
                candidate_root / raw_path,
                candidate_root / raw_path.name,
            ]
            for candidate in candidates:
                try:
                    resolved = candidate.resolve(strict=True)
                except FileNotFoundError:
                    continue
                if (
                    resolved.is_dir()
                    and resolved.is_relative_to(candidate_root)
                    and (resolved / "call.json").is_file()
                ):
                    return resolved
            for call_json in candidate_root.rglob("call.json"):
                call_folder = call_json.parent.resolve()
                if (
                    call_folder.is_relative_to(candidate_root)
                    and call_folder.name == raw_path.name
                ):
                    return call_folder

        raise FileNotFoundError(f"Call folder not found: '{call_folder_path}'")

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
        resolved_id = self.resolve_interaction_id(tenant_id, interaction_id)

        envelope = self._load_envelope(tenant_id, resolved_id)
        if not envelope:
            raise ValueError(f"Interaction {tenant_id}:{resolved_id} not found in database.")

        turns = self.transcript_repo.get_turns(tenant_id, resolved_id)
        timeline = self.timeline_repo.get_timeline(tenant_id, resolved_id)
        previous_run = None
        retry_batches: set[str] | None = None
        if retry_from_run_id is not None:
            previous_run = self.eval_repo.get_run(
                tenant_id,
                resolved_id,
                retry_from_run_id,
            )
            if previous_run is None:
                raise ValueError(
                    f"Evaluation run {retry_from_run_id} was not found for "
                    f"{tenant_id}:{resolved_id}."
                )
            retry_batches = {
                batch.batch_name
                for batch in previous_run.batches
                if batch.status == "failed"
            }

        evaluated_run = asyncio.run(
            self.registry.evaluate_batches(
                interaction=envelope,
                turns=turns,
                timeline=timeline,
                batch_names=retry_batches,
            )
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

        appointment_validation = self._derive_appointment_validation(
            envelope,
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

    def process_and_evaluate_folder(
        self,
        call_folder_path: Path | str,
        tenant_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        End-to-end on-demand pipeline:
        1. Ingest call folder (envelope + artifacts)
        2. Process & extract normalized transcript turns
        3. Reconstruct interaction timeline
        4. Calculate observability metrics & cost
        5. Run full evaluation suite
        """
        tenant_id = tenant_id or os.getenv("TENANT_ID", "health_campaign")
        folder = self._find_call_folder(call_folder_path, tenant_id)

        # Step 1: Ingestion
        envelope, artifact_rows, validation = map_call_folder(
            folder_path=folder,
            tenant_id=tenant_id,
            artifact_store=self.artifact_store,
        )
        interaction_id = envelope.interaction_id

        canonical = canonical_json(envelope)
        digest = payload_hash(canonical)

        with self.session_factory() as session:
            existing = session.scalar(
                select(InteractionRow).where(
                    InteractionRow.tenant_id == envelope.tenant_id,
                    InteractionRow.interaction_id == envelope.interaction_id,
                )
            )
            if existing:
                existing.schema_version = envelope.schema_version
                existing.payload_json = canonical
                existing.payload_hash = digest
            else:
                row = InteractionRow(
                    tenant_id=envelope.tenant_id,
                    interaction_id=envelope.interaction_id,
                    schema_version=envelope.schema_version,
                    payload_json=canonical,
                    payload_hash=digest,
                    created_at=envelope.started_at or datetime.now(timezone.utc),
                )
                session.add(row)

            existing_outbox_event = session.scalar(
                select(OutboxRow).where(
                    OutboxRow.tenant_id == envelope.tenant_id,
                    OutboxRow.interaction_id == envelope.interaction_id,
                    OutboxRow.event_type == ACCEPTED_EVENT,
                )
            )
            if not existing_outbox_event:
                session.add(
                    OutboxRow(
                        tenant_id=envelope.tenant_id,
                        interaction_id=envelope.interaction_id,
                        event_type=ACCEPTED_EVENT,
                        payload_json=canonical,
                        created_at=datetime.now(timezone.utc),
                        published_at=None,
                    )
                )

            # Store artifact metadata rows
            for art_row in artifact_rows:
                existing_art = session.scalar(
                    select(ArtifactRow).where(
                        ArtifactRow.tenant_id == art_row.tenant_id,
                        ArtifactRow.interaction_id == art_row.interaction_id,
                        ArtifactRow.artifact_id == art_row.artifact_id,
                    )
                )
                if not existing_art:
                    session.add(art_row)
            session.commit()

        # Step 2: Transcript Processing & Turns
        turns = self.processor.process_folder(folder, tenant_id=tenant_id)
        self.transcript_repo.save_turns(tenant_id, interaction_id, turns)

        # Step 3: Timeline Reconstruction
        call_metadata = {
            "agent_wav_count": validation.agent_wav_count,
            "end_reason": envelope.domain_data.get("end_reason") if envelope.domain_data else None,
            "connected_s": (
                envelope.domain_data.get("meta", {}).get("usage", {}).get("line", {}).get("connected_s")
                if envelope.domain_data else None
            ),
        }
        timeline = self.reconstructor.reconstruct(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            turns=turns,
            call_metadata=call_metadata,
        )
        self.timeline_repo.save_timeline(timeline)

        # Step 4: Observability Metrics & Cost Calculation
        metrics = self.obs_service.process_call_folder(
            call_folder=folder,
            tenant_id=tenant_id,
        )

        # Step 5: Evaluation
        evaluation_run = self.evaluate_interaction(tenant_id, interaction_id)

        return {
            "tenant_id": tenant_id,
            "interaction_id": interaction_id,
            "folder_name": folder.name,
            "turns_count": len(turns),
            "timeline_reconstructed": True,
            "metrics_calculated": True,
            "evaluation_run_id": evaluation_run.run_id,
            "evaluations_count": len(evaluation_run.batches),
            "evaluations": [
                {
                    "evaluation_id": batch.evaluation_id,
                    "batch_name": batch.batch_name,
                    "status": batch.status,
                    "result": batch.parsed_output,
                    "review_status": batch.review_status,
                    "review_reasons": batch.review_reasons,
                }
                for batch in evaluation_run.batches
            ],
        }

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
