from pathlib import Path
import subprocess
import sys

import pytest
from app.validation.golden_loader import load_golden_dataset, load_reply_wait_checks


GENERATOR = Path(__file__).resolve().parents[2] / "scripts" / "generate_golden_dataset.py"


def _generate_dataset(output_dir: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--output-dir", str(output_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_golden_dataset_csv_validation(tmp_path: Path):
    _generate_dataset(tmp_path)
    csv_path = tmp_path / "golden_dataset.csv"

    labels = load_golden_dataset(csv_path)

    # Must contain exactly 50 calls
    assert len(labels) == 50

    call_ids = [l.call_id for l in labels]
    expected_ids = [f"call_{i:02d}" for i in range(1, 51)]
    assert call_ids == expected_ids

    # Validate allowed values per spec
    allowed_what = {
        "Machine or call screener answered",
        "Heard nothing from the agent",
        "Agent's first words came late (over 3 s)",
        "Left during the first line, said nothing",
        "Said hello or a few words, then left",
        "Gave a real answer, then left before an ending",
        "Call reached an ending",
        "Can't tell",
    }
    allowed_outcome = {
        "Expert call booked",
        "Call later agreed",
        "Not interested",
        "Do not call",
        "Voicemail",
        "Call screener or machine",
        "No outcome: customer left first",
        "Can't tell",
    }
    allowed_sentiment = {"Positive", "Neutral", "Negative", "Can't tell"}
    allowed_emotion = {"Cooperative", "Confused", "Frustrated", "Disengaged", "Neutral", "Can't tell"}
    allowed_overall = {"Good", "OK", "Bad", "Can't tell"}

    for l in labels:
        assert l.what_happened in allowed_what, f"{l.call_id}: invalid what_happened '{l.what_happened}'"
        assert l.correct_outcome in allowed_outcome, f"{l.call_id}: invalid correct_outcome '{l.correct_outcome}'"
        assert l.sentiment in allowed_sentiment, f"{l.call_id}: invalid sentiment '{l.sentiment}'"
        assert l.emotion in allowed_emotion, f"{l.call_id}: invalid emotion '{l.emotion}'"
        assert l.overall in allowed_overall, f"{l.call_id}: invalid overall '{l.overall}'"

def test_reply_wait_checks_validation(tmp_path: Path):
    _generate_dataset(tmp_path)
    csv_path = tmp_path / "reply_wait_check_20_calls.csv"
    checks = load_reply_wait_checks(csv_path)

    # Exactly 20 calls per spec
    assert len(checks) == 20
    for c in checks:
        assert "call_id" in c
        assert "customer_last_word_s" in c
        assert "agent_first_sound_s" in c
        assert "gap_s" in c
        assert c["gap_s"] >= 0.0

