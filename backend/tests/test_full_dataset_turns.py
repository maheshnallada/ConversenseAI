from pathlib import Path
import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from app.reconstruction.processor import TranscriptProcessor
from app.storage.db import create_session_factory, init_db
from app.storage.orm import TurnRow
from app.storage.transcript_repo import TranscriptRepository

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "backend" / "storage" / "artifacts" / "health_campaign"


def test_full_dataset_transcript_processing():
    if not CALLS_DIR.is_dir():
        pytest.skip("External call dataset is unavailable")

    factory = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(factory)

    repo = TranscriptRepository(factory)
    processor = TranscriptProcessor()

    call_folders = sorted(
        [d for d in CALLS_DIR.iterdir() if d.is_dir() and d.name.startswith("call_")],
        key=lambda d: d.name,
    )
    assert len(call_folders) == 50

    total_turns = 0
    agent_turns = 0
    customer_turns = 0
    barge_turns = 0
    spoken_marks = {"heard": 0, "cut": 0, "not_played": 0, "no_audio": 0, "none": 0}
    empty_calls = []

    for folder in call_folders:
        turns = processor.process_folder(folder, tenant_id="tenant_verify")
        if not turns:
            empty_calls.append(folder.name)
        else:
            call_id = turns[0].interaction_id
            repo.save_turns("tenant_verify", call_id, turns)

        for t in turns:
            total_turns += 1
            if t.speaker == "agent":
                agent_turns += 1
                if t.playback_spoken is None:
                    spoken_marks["none"] += 1
                else:
                    assert t.playback_spoken in {
                        "heard",
                        "cut",
                        "not_played",
                        "no_audio",
                    }, (
                        f"Unexpected playback status: {t.playback_spoken!r}"
                    )
                    spoken_marks[t.playback_spoken] += 1
            elif t.speaker == "customer":
                customer_turns += 1

            if t.barged_in is True:
                barge_turns += 1

    # Exact facts verified from Phase 0 inspection & Spec
    assert total_turns == 399
    assert agent_turns == 230
    assert customer_turns == 169
    assert spoken_marks["heard"] == 95
    assert spoken_marks["cut"] == 55
    assert spoken_marks["not_played"] == 10
    assert spoken_marks["no_audio"] == 1
    assert spoken_marks["none"] == 69  # Exactly 69 assistant messages have no spoken marks (12 studio calls)
    assert set(empty_calls) == {"call_13", "call_25"}
    assert barge_turns == 44

    # Verify database persistence
    with factory() as session:
        stored_count = session.scalar(select(func.count(TurnRow.id)))
        assert stored_count == 399

