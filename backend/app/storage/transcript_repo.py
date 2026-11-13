import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.domain.transcript import TranscriptTurn
from app.storage.orm import TurnRow


class TranscriptRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def save_turns(
        self,
        tenant_id: str,
        interaction_id: str,
        turns: list[TranscriptTurn],
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            # Delete existing turns for idempotency
            session.execute(
                delete(TurnRow).where(
                    TurnRow.tenant_id == tenant_id,
                    TurnRow.interaction_id == interaction_id,
                )
            )

            for t in turns:
                meta_str = json.dumps(t.metadata) if t.metadata else None
                row = TurnRow(
                    tenant_id=tenant_id,
                    interaction_id=interaction_id,
                    turn_id=t.turn_id,
                    turn_index=t.turn_index,
                    speaker=t.speaker,
                    raw_text=t.raw_text,
                    normalized_text=t.normalized_text,
                    start_s=t.start_s,
                    end_s=t.end_s,
                    duration_s=t.duration_s,
                    playback_spoken=t.playback_spoken,
                    playback_heard_text=t.playback_heard_text,
                    audio_s=t.audio_s,
                    barged_in=t.barged_in,
                    metadata_json=meta_str,
                    created_at=now,
                )
                session.add(row)
            session.commit()

    def get_turns(self, tenant_id: str, interaction_id: str) -> list[TranscriptTurn]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(TurnRow)
                .where(
                    TurnRow.tenant_id == tenant_id,
                    TurnRow.interaction_id == interaction_id,
                )
                .order_by(TurnRow.turn_index.asc())
            ).all()

            turns: list[TranscriptTurn] = []
            for r in rows:
                meta = json.loads(r.metadata_json) if r.metadata_json else {}
                turns.append(
                    TranscriptTurn(
                        turn_id=r.turn_id,
                        interaction_id=r.interaction_id,
                        tenant_id=r.tenant_id,
                        turn_index=r.turn_index,
                        speaker=r.speaker,
                        raw_text=r.raw_text,
                        normalized_text=r.normalized_text,
                        start_s=r.start_s,
                        end_s=r.end_s,
                        duration_s=r.duration_s,
                        playback_spoken=r.playback_spoken,
                        playback_heard_text=r.playback_heard_text,
                        audio_s=r.audio_s,
                        barged_in=r.barged_in,
                        metadata=meta,
                    )
                )
            return turns

