from pathlib import Path
import pytest

from app.reconstruction.processor import TranscriptProcessor

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALLS_DIR = PROJECT_ROOT / "data" / "calls"


def _call_dir(call_id: str) -> Path:
    call_dir = CALLS_DIR / call_id
    if not call_dir.is_dir():
        pytest.skip("External call dataset is unavailable")
    return call_dir


def test_process_call_01_standard():
    call_dir = _call_dir("call_01")
    processor = TranscriptProcessor()
    turns = processor.process_folder(call_dir, tenant_id="tenant_test")

    # call_01 has 7 messages (4 assistant, 3 customer)
    assert len(turns) == 7

    # Turn 0 is assistant
    t0 = turns[0]
    assert t0.turn_index == 0
    assert t0.speaker == "agent"
    assert t0.raw_text != ""
    assert t0.normalized_text != ""
    assert t0.start_s is not None
    assert t0.playback_spoken in ["heard", "cut", "not_played", "no_audio"]

    # Customer turn
    customer_turns = [t for t in turns if t.speaker == "customer"]
    assert len(customer_turns) == 3
    for ct in customer_turns:
        assert ct.playback_spoken is None  # Customer lines don't have agent spoken marks
        assert ct.audio_s is None or ct.audio_s > 0

    # Agent turns
    agent_turns = [t for t in turns if t.speaker == "agent"]
    assert len(agent_turns) == 4
    spoken_statuses = [t.playback_spoken for t in agent_turns]
    # Phase 0 noted call_01 has heard 1, cut 2, not_played 1
    assert spoken_statuses.count("heard") == 1
    assert spoken_statuses.count("cut") == 2
    assert spoken_statuses.count("not_played") == 1


def test_process_call_05_studio_no_spoken_marks():
    call_dir = _call_dir("call_05")
    processor = TranscriptProcessor()
    turns = processor.process_folder(call_dir, tenant_id="tenant_test")

    # call_05 has 59 messages (32 assistant, 27 user)
    assert len(turns) == 59
    agent_turns = [t for t in turns if t.speaker == "agent"]
    assert len(agent_turns) == 32
    # In studio calls, metadata.spoken is absent on all assistant lines
    for at in agent_turns:
        assert at.playback_spoken is None  # Must NOT be fabricated as not_played!


def test_process_call_13_silent_call():
    call_dir = _call_dir("call_13")
    processor = TranscriptProcessor()
    turns = processor.process_folder(call_dir, tenant_id="tenant_test")
    # call_13 has 0 messages
    assert len(turns) == 0

