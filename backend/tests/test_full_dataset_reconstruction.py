import json
from pathlib import Path
import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from app.reconstruction.processor import TranscriptProcessor
from app.reconstruction.reconstructor import TimelineReconstructor
from app.storage.db import create_session_factory, init_db
from app.storage.orm import InteractionTimelineRow
from app.storage.timeline_repo import TimelineRepository
from app.validation.audio import validate_call_files

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "data" / "calls"


def test_full_dataset_timeline_reconstruction():
    assert CALLS_DIR.exists()

    factory = create_session_factory("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(factory)

    repo = TimelineRepository(factory)
    processor = TranscriptProcessor()
    reconstructor = TimelineReconstructor()

    call_folders = sorted(
        [d for d in CALLS_DIR.iterdir() if d.is_dir() and d.name.startswith("call_")],
        key=lambda d: d.name,
    )
    assert len(call_folders) == 50

    reconstructed_count = 0
    no_agent_audio_calls = []

    for folder in call_folders:
        with open(folder / "call.json", "r", encoding="utf-8") as f:
            call_data = json.load(f)

        call_id = call_data["call_id"]
        val = validate_call_files(folder)

        call_meta = {
            "agent_wav_count": val.agent_wav_count,
            "end_reason": call_data.get("end_reason"),
            "connected_s": call_data.get("meta", {}).get("usage", {}).get("line", {}).get("connected_s"),
        }

        turns = processor.process_folder(folder, tenant_id="tenant_verify")
        timeline = reconstructor.reconstruct(
            tenant_id="tenant_verify",
            interaction_id=call_id,
            turns=turns,
            call_metadata=call_meta,
        )

        repo.save_timeline(timeline)
        reconstructed_count += 1

        if (
            timeline.first_technical_failure
            and timeline.first_technical_failure.failure_type == "NO_AGENT_AUDIO"
        ):
            no_agent_audio_calls.append(folder.name)

    # All 50 calls have timelines
    assert reconstructed_count == 50

    # Exactly the 7 calls without agent audio must have first_technical_failure == "NO_AGENT_AUDIO"
    expected_no_agent = {"call_12", "call_13", "call_25", "call_31", "call_32", "call_43", "call_47"}
    assert set(no_agent_audio_calls) == expected_no_agent

    # Verify database persistence
    with factory() as session:
        stored_count = session.scalar(select(func.count(InteractionTimelineRow.id)))
        assert stored_count == 50

