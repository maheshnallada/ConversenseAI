import csv
import json
import subprocess
import sys
from pathlib import Path


GENERATOR = Path(__file__).resolve().parents[2] / "scripts" / "generate_golden_dataset.py"
REPLY_CHECK_CALLS = (
    "call_01", "call_02", "call_03", "call_04", "call_05",
    "call_06", "call_07", "call_08", "call_09", "call_10",
    "call_11", "call_12", "call_14", "call_15", "call_16",
    "call_17", "call_18", "call_19", "call_20", "call_21",
)


def _prepare_call_inputs(root: Path, *, missing_call: str | None = None, null_call: str | None = None) -> None:
    call_root = root / "data" / "calls"
    call_root.mkdir(parents=True)
    for call_id in REPLY_CHECK_CALLS:
        if call_id == missing_call:
            continue
        messages = None if call_id == null_call else []
        call_dir = call_root / call_id
        call_dir.mkdir()
        (call_dir / "call.json").write_text(
            json.dumps({"messages": messages}),
            encoding="utf-8",
        )


def test_generation_failure_preserves_existing_golden_csv(tmp_path: Path) -> None:
    _prepare_call_inputs(tmp_path, missing_call="call_21")
    golden_csv = tmp_path / "data" / "golden_dataset.csv"
    sentinel = b"existing golden dataset\n"
    golden_csv.write_bytes(sentinel)

    result = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert golden_csv.read_bytes() == sentinel


def test_generation_accepts_null_messages(tmp_path: Path) -> None:
    _prepare_call_inputs(tmp_path, null_call="call_02")

    result = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    golden_csv = tmp_path / "data" / "golden_dataset.csv"
    reply_csv = tmp_path / "data" / "reply_wait_check_20_calls.csv"
    assert result.returncode == 0, result.stderr
    with golden_csv.open(newline="", encoding="utf-8") as file:
        assert len(list(csv.reader(file))) == 51
    with reply_csv.open(newline="", encoding="utf-8") as file:
        assert len(list(csv.reader(file))) == 1
