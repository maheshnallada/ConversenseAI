import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.envelope import InteractionEvent
from app.domain.transcript import TranscriptTurn
from app.storage.interaction_errors import InteractionNotFound
from app.storage.orm import InteractionEventRow, InteractionRow
from app.storage.transcript_repo import TranscriptRepository, TranscriptTurnConflict


class EventConflict(Exception):
    def __init__(self, tenant_id: str, interaction_id: str, event_id: str) -> None:
        super().__init__(f"Event {event_id!r} was already registered with different content")
        self.tenant_id = tenant_id
        self.interaction_id = interaction_id
        self.event_id = event_id


def _canonical_event(event: InteractionEvent) -> tuple[str, str | None, str]:
    serialized = json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    payload_json = (
        json.dumps(
            event.payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        if event.payload is not None
        else None
    )
    return serialized, payload_json, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class EventRepository:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory
        self._transcript_repo = TranscriptRepository(session_factory)

    def append(
        self,
        tenant_id: str,
        interaction_id: str,
        event: InteractionEvent,
        transcript_turn: TranscriptTurn | None = None,
    ) -> bool:
        serialized, payload_json, event_hash = _canonical_event(event)
        try:
            with self._session_factory.begin() as session:
                self._require_interaction(session, tenant_id, interaction_id)
                existing = self._find_event(
                    session, tenant_id, interaction_id, event.event_id
                )
                if existing is not None:
                    if existing.event_hash != event_hash:
                        raise EventConflict(tenant_id, interaction_id, event.event_id)
                    created = False
                else:
                    session.add(
                        InteractionEventRow(
                            tenant_id=tenant_id,
                            interaction_id=interaction_id,
                            event_id=event.event_id,
                            event_type=event.event_type,
                            occurred_at=event.occurred_at,
                            payload_json=payload_json,
                            event_hash=event_hash,
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                    created = True

                if transcript_turn is not None:
                    self._transcript_repo.save_turn(transcript_turn, session=session)
                return created
        except IntegrityError:
            with self._session_factory() as session:
                existing = self._find_event(
                    session, tenant_id, interaction_id, event.event_id
                )
                if existing is None:
                    raise
                if existing.event_hash != event_hash:
                    raise EventConflict(tenant_id, interaction_id, event.event_id)
            return self.append(
                tenant_id, interaction_id, event, transcript_turn=transcript_turn
            )

    @staticmethod
    def _require_interaction(session: Session, tenant_id: str, interaction_id: str) -> None:
        exists = session.scalar(
            select(InteractionRow.id).where(
                InteractionRow.tenant_id == tenant_id,
                InteractionRow.interaction_id == interaction_id,
            )
        )
        if exists is None:
            raise InteractionNotFound(tenant_id, interaction_id)

    @staticmethod
    def _find_event(
        session: Session, tenant_id: str, interaction_id: str, event_id: str
    ) -> InteractionEventRow | None:
        return session.scalar(
            select(InteractionEventRow).where(
                InteractionEventRow.tenant_id == tenant_id,
                InteractionEventRow.interaction_id == interaction_id,
                InteractionEventRow.event_id == event_id,
            )
        )
