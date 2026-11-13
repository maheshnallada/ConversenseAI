from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.domain.golden import GoldenCallLabel
from app.storage.golden_repo import GoldenDatasetRepository

@pytest.fixture
def repo():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return GoldenDatasetRepository(factory)

def test_golden_call_label_save_and_retrieve(repo):
    label = GoldenCallLabel(
        call_id="call_test_01",
        interaction_id="uuid-test-01",
        what_happened="Call reached an ending",
        correct_outcome="Not interested",
        facts_customer_gave="Policy: none",
        sentiment="Negative",
        emotion="Disengaged",
        overall="OK",
        first_thing_wrong_line=3,
        first_thing_wrong_what="Agent line was cut.",
        never_rule_broken="None",
        reviewer_notes="Customer said no multiple times.",
    )

    repo.save_label(label)
    retrieved = repo.get_by_call_id("call_test_01")

    assert retrieved is not None
    assert retrieved.call_id == "call_test_01"
    assert retrieved.interaction_id == "uuid-test-01"
    assert retrieved.correct_outcome == "Not interested"
    assert retrieved.what_happened == "Call reached an ending"
    assert retrieved.first_thing_wrong_line == 3
    assert retrieved.never_rule_broken == "None"

def test_golden_dataset_save_many_and_get_all(repo):
    l1 = GoldenCallLabel(
        call_id="call_test_m1",
        what_happened="Call reached an ending",
        correct_outcome="Expert call booked",
        facts_customer_gave="Cover for parents",
        sentiment="Positive",
        emotion="Cooperative",
        overall="Good",
        never_rule_broken="None",
    )
    l2 = GoldenCallLabel(
        call_id="call_test_m2",
        what_happened="Heard nothing from the agent",
        correct_outcome="No outcome: customer left first",
        facts_customer_gave="",
        sentiment="Neutral",
        emotion="Neutral",
        overall="Bad",
        never_rule_broken="None",
    )

    repo.save_many([l1, l2])
    all_labels = repo.get_all()
    call_ids = {l.call_id for l in all_labels}

    assert "call_test_m1" in call_ids
    assert "call_test_m2" in call_ids

