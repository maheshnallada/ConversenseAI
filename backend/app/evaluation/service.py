import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationResult
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
    ):
        self.session_factory = session_factory
        self.registry = registry or EvaluatorRegistry()
        self.eval_repo = EvaluationRepository(session_factory)
        self.transcript_repo = TranscriptRepository(session_factory)
        self.timeline_repo = TimelineRepository(session_factory)
        self.obs_repo = ObservabilityRepository(session_factory)

        root = Path(__file__).resolve().parent.parent.parent.parent
        artifact_root = os.getenv("ARTIFACT_STORAGE_PATH") or root / "data" / "artifact_store"
        self.artifact_store = artifact_store or LocalArtifactStore(artifact_root)
        self.rate_card_manager = rate_card_manager or RateCardManager(root / "configs" / "rate_cards.json")
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

    def evaluate_interaction(self, tenant_id: str, interaction_id: str) -> List[EvaluationResult]:
        """
        Loads an existing interaction and its context, runs all evaluators,
        persists the results, and returns them.
        """
        resolved_id = self.resolve_interaction_id(tenant_id, interaction_id)

        # 1. Load interaction envelope
        envelope = self._load_envelope(tenant_id, resolved_id)
        if not envelope:
            raise ValueError(f"Interaction {tenant_id}:{resolved_id} not found in database.")

        # 2. Load turns
        turns = self.transcript_repo.get_turns(tenant_id, resolved_id)

        # 3. Load timeline
        timeline = self.timeline_repo.get_timeline(tenant_id, resolved_id)

        # 4. Run evaluators
        results = self.registry.evaluate_all(
            interaction=envelope,
            turns=turns,
            timeline=timeline,
        )

        # 5. Persist results
        self.eval_repo.save_many(results)

        return results

    def process_and_evaluate_folder(
        self,
        call_folder_path: Path | str,
        tenant_id: str = "health_campaign",
    ) -> Dict[str, Any]:
        """
        End-to-end on-demand pipeline:
        1. Ingest call folder (envelope + artifacts)
        2. Process & extract normalized transcript turns
        3. Reconstruct interaction timeline
        4. Calculate observability metrics & cost
        5. Run full evaluation suite
        """
        folder = Path(call_folder_path).resolve()
        if not folder.exists() or not folder.is_dir():
            raise FileNotFoundError(f"Call folder not found: {folder}")

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
        evaluations = self.evaluate_interaction(tenant_id, interaction_id)

        return {
            "tenant_id": tenant_id,
            "interaction_id": interaction_id,
            "folder_name": folder.name,
            "turns_count": len(turns),
            "timeline_reconstructed": True,
            "metrics_calculated": True,
            "evaluations_count": len(evaluations),
            "evaluations": [
                {
                    "family": e.family,
                    "evaluator_id": e.evaluator_id,
                    "label": e.label,
                    "score": e.score,
                    "review_status": e.review_status,
                    "reason": e.reason,
                    "details": e.details,
                }
                for e in evaluations
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
