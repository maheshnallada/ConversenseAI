from datetime import datetime, timezone
import pytest
from sqlalchemy.pool import StaticPool

from app.domain.transcript import TranscriptTurn
from app.storage.db import create_session_factory, init_db
from app.storage.transcript_repo import TranscriptRepository


def _factory():
    f = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(f)
    return f


def test_save_and_get_turns():
    factory = _factory()
    repo = TranscriptRepository(factory)

    turns = [
        TranscriptTurn(
            turn_id="turn_0",
            interaction_id="inter_1",
            tenant_id="tenant_1",
            turn_index=0,
            speaker="agent",
            raw_text="नमस्ते, क्या मैं बात कर सकता हूँ?",
            normalized_text="नमस्ते, क्या मैं बात कर सकता हूँ?",
            start_s=0.5,
            end_s=2.5,
            duration_s=2.0,
            playback_spoken="heard",
            audio_s=2.0,
            barged_in=False,
            metadata={"source": "assistant:livekit"},
        ),
        TranscriptTurn(
            turn_id="turn_1",
            interaction_id="inter_1",
            tenant_id="tenant_1",
            turn_index=1,
            speaker="customer",
            raw_text="हाँ बोलिए।",
            normalized_text="हाँ बोलिए।",
            start_s=2.8,
            end_s=3.5,
            duration_s=0.7,
            playback_spoken=None,  # Customer turns have no spoken marks
            audio_s=None,
            barged_in=None,
            metadata={"source": "user:livekit"},
        ),
    ]

    # Save turns
    repo.save_turns("tenant_1", "inter_1", turns)

    # Fetch turns
    retrieved = repo.get_turns("tenant_1", "inter_1")
    assert len(retrieved) == 2
    assert retrieved[0].turn_id == "turn_0"
    assert retrieved[0].speaker == "agent"
    assert retrieved[0].playback_spoken == "heard"
    assert retrieved[0].start_s == 0.5
    assert retrieved[0].raw_text == "नमस्ते, क्या मैं बात कर सकता हूँ?"

    assert retrieved[1].turn_id == "turn_1"
    assert retrieved[1].speaker == "customer"
    assert retrieved[1].playback_spoken is None


def test_save_turns_idempotency():
    factory = _factory()
    repo = TranscriptRepository(factory)

    turn = TranscriptTurn(
        turn_id="turn_0",
        interaction_id="inter_1",
        tenant_id="tenant_1",
        turn_index=0,
        speaker="agent",
        raw_text="Hello",
        normalized_text="hello",
        start_s=1.0,
    )

    repo.save_turns("tenant_1", "inter_1", [turn])
    # Saving again should replace cleanly without unique constraint violation
    repo.save_turns("tenant_1", "inter_1", [turn])

    retrieved = repo.get_turns("tenant_1", "inter_1")
    assert len(retrieved) == 1

