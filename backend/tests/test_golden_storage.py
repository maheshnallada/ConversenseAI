from contextlib import contextmanager

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError

from app.domain.golden import GoldenCallLabel
from app.storage.golden_repo import GoldenDatasetRepository

@pytest.fixture
def repo(session_factory):
    return GoldenDatasetRepository(session_factory)

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


def test_save_many_rolls_back_entire_batch_on_invalid_label(repo):
    valid = GoldenCallLabel(
        call_id="call_test_atomic_valid",
        what_happened="Call reached an ending",
        correct_outcome="Not interested",
    )
    invalid = GoldenCallLabel(
        call_id="call_test_atomic_invalid",
        what_happened=None,
        correct_outcome="Not interested",
    )

    with pytest.raises(IntegrityError):
        repo.save_many([valid, invalid])

    assert repo.get_by_call_id(valid.call_id) is None


@pytest.mark.parametrize("dialect_type", [sqlite.dialect, postgresql.dialect])
def test_save_many_uses_native_upsert_for_supported_dialects(dialect_type):
    captured_statements = []

    class FakeSession:
        def get_bind(self):
            return type("Bind", (), {"dialect": dialect_type()})()

        def execute(self, statement, values):
            compiled = str(statement.compile(dialect=dialect_type()))
            captured_statements.append((compiled, values))

    class FakeSessionFactory:
        @contextmanager
        def begin(self):
            yield FakeSession()

    label = GoldenCallLabel(
        call_id="call_test_upsert",
        what_happened="Call reached an ending",
        correct_outcome="Not interested",
    )

    GoldenDatasetRepository(FakeSessionFactory()).save_many([label])

    assert len(captured_statements) == 1
    sql, values = captured_statements[0]
    assert "ON CONFLICT (call_id) DO UPDATE" in sql
    assert values[0]["call_id"] == label.call_id

