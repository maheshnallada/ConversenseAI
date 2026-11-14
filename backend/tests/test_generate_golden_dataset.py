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
        [
            sys.executable,
            str(GENERATOR),
            "--data-dir",
            str(tmp_path / "data" / "calls"),
            "--output-dir",
            str(tmp_path / "data"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert golden_csv.read_bytes() == sentinel


def test_generation_accepts_null_messages(tmp_path: Path) -> None:
    _prepare_call_inputs(tmp_path, null_call="call_02")

    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--data-dir",
            str(tmp_path / "data" / "calls"),
            "--output-dir",
            str(tmp_path / "data"),
        ],
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


def test_reply_wait_uses_manifest_end_and_agent_audio_start(tmp_path: Path) -> None:
    _prepare_call_inputs(tmp_path)
    call_folder = tmp_path / "data" / "calls" / "call_01"
    (call_folder / "call.json").write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "t": 2.0, "metadata": {"turn": 1}},
                    {"role": "assistant", "t": 4.5, "metadata": {"turn": 1}},
                ]
            }
        ),
        encoding="utf-8",
    )
    (call_folder / "manifest.jsonl").write_text(
        json.dumps({"turn": 1, "seconds": 3.25}) + "\n",
        encoding="utf-8",
    )
    (call_folder / "agent_manifest.jsonl").write_text(
        json.dumps({"turn": 1, "at_s": 4.0}) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--data-dir",
            str(tmp_path / "data" / "calls"),
            "--output-dir",
            str(tmp_path / "generated"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    reply_csv = tmp_path / "generated" / "reply_wait_check_20_calls.csv"
    assert result.returncode == 0, result.stderr
    with reply_csv.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["Customer last word (s)"] == "3.25"
    assert rows[0]["Agent first sound (s)"] == "4.0"
    assert rows[0]["Gap (s)"] == "0.75"


def test_generation_defaults_to_bundled_artifacts_and_creates_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated" / "dataset"
    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--output-dir",
            str(output_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    with (output_dir / "golden_dataset.csv").open(newline="", encoding="utf-8") as file:
        assert len(list(csv.reader(file))) == 51
    with (output_dir / "reply_wait_check_20_calls.csv").open(
        newline="", encoding="utf-8"
    ) as file:
        assert len(list(csv.reader(file))) == 21
