import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.envelope import InteractionEvent
from app.domain.transcript import TranscriptTurn
from app.storage.orm import TurnRow


class TranscriptTurnConflict(Exception):
    def __init__(self, tenant_id: str, interaction_id: str, turn_index: int) -> None:
        super().__init__(
            f"Transcript turn {turn_index} was already registered with different content"
        )
        self.tenant_id = tenant_id
        self.interaction_id = interaction_id
        self.turn_index = turn_index


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

    @staticmethod
    def event_turn(
        tenant_id: str,
        interaction_id: str,
        event: InteractionEvent,
    ) -> TranscriptTurn:
        payload = event.payload
        if payload is None:
            raise ValueError("transcript.turn events require a payload")

        turn_id = payload.get("turn_id")
        turn_index = payload.get("turn_index")
        raw_text = payload.get("raw_text")
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("transcript.turn payload requires a non-empty turn_id")
        if (
            not isinstance(turn_index, int)
            or isinstance(turn_index, bool)
            or turn_index < 0
        ):
            raise ValueError("transcript.turn payload requires a non-negative turn_index")
        if not isinstance(raw_text, str):
            raise ValueError("transcript.turn payload requires raw_text")

        speaker = payload.get("speaker")
        if not isinstance(speaker, str) or not speaker.strip():
            speaker = "unknown"
        normalized_text = payload.get("normalized_text")
        if normalized_text is None:
            normalized_text = raw_text
        if not isinstance(normalized_text, str):
            raise ValueError("transcript.turn normalized_text must be a string")

        optional_values: dict[str, Any] = {}
        for field in ("start_s", "end_s", "duration_s", "audio_s"):
            value = payload.get(field)
            if value is not None and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
            ):
                raise ValueError(f"transcript.turn {field} must be a number")
            optional_values[field] = value

        for field in ("playback_spoken", "playback_heard_text"):
            value = payload.get(field)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"transcript.turn {field} must be a string")
            optional_values[field] = value

        barged_in = payload.get("barged_in")
        if barged_in is not None and not isinstance(barged_in, bool):
            raise ValueError("transcript.turn barged_in must be a boolean")
        metadata = payload.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("transcript.turn metadata must be an object")

        return TranscriptTurn(
            turn_id=turn_id,
            interaction_id=interaction_id,
            tenant_id=tenant_id,
            turn_index=turn_index,
            speaker=speaker,
            raw_text=raw_text,
            normalized_text=normalized_text,
            start_s=optional_values["start_s"],
            end_s=optional_values["end_s"],
            duration_s=optional_values["duration_s"],
            playback_spoken=optional_values["playback_spoken"],
            playback_heard_text=optional_values["playback_heard_text"],
            audio_s=optional_values["audio_s"],
            barged_in=barged_in,
            metadata=metadata,
        )

    def save_turn(
        self,
        turn: TranscriptTurn,
        session: Session | None = None,
    ) -> bool:
        if session is None:
            with self.session_factory.begin() as managed_session:
                return self.save_turn(turn, session=managed_session)

        existing = session.scalar(
            select(TurnRow).where(
                TurnRow.tenant_id == turn.tenant_id,
                TurnRow.interaction_id == turn.interaction_id,
                TurnRow.turn_index == turn.turn_index,
            )
        )
        if existing is not None:
            if not self._matches_turn(existing, turn):
                raise TranscriptTurnConflict(
                    turn.tenant_id, turn.interaction_id, turn.turn_index
                )
            return False

        session.add(self._turn_row(turn))
        return True

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

    @staticmethod
    def _turn_row(turn: TranscriptTurn) -> TurnRow:
        meta_str = (
            json.dumps(turn.metadata, sort_keys=True, ensure_ascii=False)
            if turn.metadata
            else None
        )
        return TurnRow(
            tenant_id=turn.tenant_id,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
            speaker=turn.speaker,
            raw_text=turn.raw_text,
            normalized_text=turn.normalized_text,
            start_s=turn.start_s,
            end_s=turn.end_s,
            duration_s=turn.duration_s,
            playback_spoken=turn.playback_spoken,
            playback_heard_text=turn.playback_heard_text,
            audio_s=turn.audio_s,
            barged_in=turn.barged_in,
            metadata_json=meta_str,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _matches_turn(row: TurnRow, turn: TranscriptTurn) -> bool:
        existing_metadata = json.loads(row.metadata_json) if row.metadata_json else {}
        return (
            row.turn_id == turn.turn_id
            and row.speaker == turn.speaker
            and row.raw_text == turn.raw_text
            and row.normalized_text == turn.normalized_text
            and row.start_s == turn.start_s
            and row.end_s == turn.end_s
            and row.duration_s == turn.duration_s
            and row.playback_spoken == turn.playback_spoken
            and row.playback_heard_text == turn.playback_heard_text
            and row.audio_s == turn.audio_s
            and row.barged_in == turn.barged_in
            and existing_metadata == turn.metadata
        )

