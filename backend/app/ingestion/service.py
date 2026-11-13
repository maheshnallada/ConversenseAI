import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.domain.envelope import InteractionEnvelope
from app.ingestion.errors import IdempotencyConflict
from app.storage.orm import InteractionRow, OutboxRow

ACCEPTED_EVENT = "interaction.accepted"


def canonical_json(envelope: InteractionEnvelope) -> str:
    payload = envelope.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IngestResult:
    created: bool
    interaction: InteractionEnvelope


class IngestionService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def ingest(self, envelope: InteractionEnvelope) -> IngestResult:
        canonical = canonical_json(envelope)
        digest = payload_hash(canonical)
        with self._session_factory() as session:
            existing = self._find(session, envelope.tenant_id, envelope.interaction_id)
            if existing is not None:
                return self._replay_or_conflict(existing, digest)

            now = datetime.now(timezone.utc)
            session.add(
                InteractionRow(
                    tenant_id=envelope.tenant_id,
                    interaction_id=envelope.interaction_id,
                    schema_version=envelope.schema_version,
                    payload_json=canonical,
                    payload_hash=digest,
                    created_at=now,
                )
            )
            session.add(
                OutboxRow(
                    tenant_id=envelope.tenant_id,
                    interaction_id=envelope.interaction_id,
                    event_type=ACCEPTED_EVENT,
                    payload_json=canonical,
                    created_at=now,
                    published_at=None,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = self._find(session, envelope.tenant_id, envelope.interaction_id)
                if existing is None:
                    raise
                return self._replay_or_conflict(existing, digest)
            return IngestResult(created=True, interaction=envelope)

    def get(self, tenant_id: str, interaction_id: str) -> InteractionEnvelope | None:
        with self._session_factory() as session:
            row = self._find(session, tenant_id, interaction_id)
            if row is None:
                return None
            return InteractionEnvelope.model_validate_json(row.payload_json)

    def outbox_count(self, tenant_id: str, interaction_id: str) -> int:
        return self._count(tenant_id, interaction_id, unpublished_only=False)

    def unpublished_outbox_count(self, tenant_id: str, interaction_id: str) -> int:
        return self._count(tenant_id, interaction_id, unpublished_only=True)

    def _count(self, tenant_id: str, interaction_id: str, unpublished_only: bool) -> int:
        with self._session_factory() as session:
            query = select(func.count()).select_from(OutboxRow).where(
                OutboxRow.tenant_id == tenant_id,
                OutboxRow.interaction_id == interaction_id,
            )
            if unpublished_only:
                query = query.where(OutboxRow.published_at.is_(None))
            return int(session.scalar(query) or 0)

    def _find(self, session, tenant_id: str, interaction_id: str) -> InteractionRow | None:
        return session.scalar(
            select(InteractionRow).where(
                InteractionRow.tenant_id == tenant_id,
                InteractionRow.interaction_id == interaction_id,
            )
        )

    def _replay_or_conflict(self, existing: InteractionRow, digest: str) -> IngestResult:
        if existing.payload_hash != digest:
            raise IdempotencyConflict(existing.tenant_id, existing.interaction_id)
        return IngestResult(
            created=False,
            interaction=InteractionEnvelope.model_validate_json(existing.payload_json),
        )
