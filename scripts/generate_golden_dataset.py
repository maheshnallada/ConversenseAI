import argparse
import csv
import json
import math
import os
import tempfile
from pathlib import Path

# Build 50 calls golden dataset
golden_rows = [
    # Call 01 - 05 from reviewed draft
    ["call_01", "Call reached an ending", "Not interested", "Policy: none; no callback agreed.", "Negative", "Disengaged", "OK", 3, "Agent main introduction cut.", "None"],
    ["call_02", "Gave a real answer, then left before an ending", "Expert call booked", "Policy: own/self-purchased; cover: family; callback: 2026-11-07 11:00.", "Neutral", "Cooperative", "OK", 19, "Booking confirmation line was cut.", "None"],
    ["call_03", "Said hello or a few words, then left", "No outcome: customer left first", "", "Neutral", "Disengaged", "Bad", 3, "Agent substantive question marked not_played.", "None"],
    ["call_04", "Said hello or a few words, then left", "No outcome: customer left first", "Customer asked who was calling.", "Neutral", "Confused", "Bad", 3, "Agent opening explanation was cut before completion.", "None"],
    ["call_05", "Call reached an ending", "Expert call booked", "Policy: none; callback: 2026-11-03 11:00; location: Bengal.", "Neutral", "Confused", "Bad", 1, "Agent opened with promotional claim without introducing self.", "Pushed a policy or insurer"],
    # Call 06 - 10
    ["call_06", "Call reached an ending", "Not interested", "Policy: none; customer declined politely.", "Neutral", "Disengaged", "OK", 5, "Repeat prompt after customer spoke.", "None"],
    ["call_07", "Gave a real answer, then left before an ending", "No outcome: customer left first", "", "Neutral", "Disengaged", "Bad", 3, "Agent line cut during interruption.", "None"],
    ["call_08", "Gave a real answer, then left before an ending", "No outcome: customer left first", "Customer asked company name.", "Neutral", "Confused", "OK", 5, "Customer question unanswered before hangup.", "None"],
    ["call_09", "Said hello or a few words, then left", "No outcome: customer left first", "", "Neutral", "Disengaged", "OK", 3, "Agent speech interrupted.", "None"],
    ["call_10", "Call reached an ending", "Expert call booked", "Policy: health insurance needed; callback agreed.", "Positive", "Cooperative", "Good", "", "", "None"],
    # Call 11 - 15
    ["call_11", "Call reached an ending", "Not interested", "Customer stated clearly: 'mujhe nahi janna hai'.", "Negative", "Frustrated", "Bad", 3, "Customer requested to stop immediately.", "None"],
    ["call_12", "Agent's first words came late (over 3 s)", "No outcome: customer left first", "", "Neutral", "Disengaged", "Bad", 1, "Agent first speech delayed over 3s, no agent audio files.", "None"],
    ["call_13", "Heard nothing from the agent", "No outcome: customer left first", "", "Can't tell", "Neutral", "Bad", 1, "Call unanswered with zero audio.", "None"],
    ["call_14", "Agent's first words came late (over 3 s)", "No outcome: customer left first", "", "Neutral", "Disengaged", "Bad", 1, "Initial agent latency exceeded 3s.", "None"],
    ["call_15", "Call reached an ending", "Not interested", "Policy: not required currently.", "Neutral", "Disengaged", "OK", 3, "Agent audio cut on turn 3.", "None"],
    # Call 16 - 20
    ["call_16", "Said hello or a few words, then left", "No outcome: customer left first", "", "Neutral", "Disengaged", "OK", 3, "Call dropped early after greeting.", "None"],
    ["call_17", "Gave a real answer, then left before an ending", "No outcome: customer left first", "", "Neutral", "Neutral", "Bad", 1, "Studio call without proper greeting delivery.", "None"],
    ["call_18", "Gave a real answer, then left before an ending", "No outcome: customer left first", "Customer asked interest rate / plan details.", "Neutral", "Confused", "OK", 5, "Agent did not directly clarify plan details.", "None"],
    ["call_19", "Call reached an ending", "Not interested", "Customer said: 'nahi chahiye madam'.", "Neutral", "Disengaged", "OK", 3, "Customer politely declined.", "None"],
    ["call_20", "Machine or call screener answered", "Call screener or machine", "Call screener prompt heard.", "Neutral", "Neutral", "OK", 1, "Google call screener answered call.", "None"],
    # Call 21 - 25
    ["call_21", "Gave a real answer, then left before an ending", "No outcome: customer left first", "Officer mention in transcript.", "Neutral", "Neutral", "OK", 5, "Customer disconnected unexpectedly.", "None"],
    ["call_22", "Call reached an ending", "Not interested", "Customer confirmed no interest.", "Neutral", "Disengaged", "OK", 5, "Customer hung up after declining.", "None"],
    ["call_23", "Gave a real answer, then left before an ending", "Not interested", "Customer asked where agent is calling from.", "Neutral", "Confused", "OK", 5, "Identity clarification delayed.", "None"],
    ["call_24", "Said hello or a few words, then left", "No outcome: customer left first", "Customer asked who is speaking.", "Neutral", "Confused", "OK", 3, "Customer dropped before introduction.", "None"],
    ["call_25", "Heard nothing from the agent", "No outcome: customer left first", "", "Can't tell", "Neutral", "Bad", 1, "Call unanswered with zero audio.", "None"],
    # Call 26 - 30
    ["call_26", "Call reached an ending", "Not interested", "Identity: Ranveer Singh (wrong person).", "Neutral", "Neutral", "OK", 5, "Wrong number identified.", "None"],
    ["call_27", "Gave a real answer, then left before an ending", "No outcome: customer left first", "Customer stated address wrong.", "Neutral", "Disengaged", "OK", 3, "Customer disconnected during address inquiry.", "None"],
    ["call_28", "Call reached an ending", "Do not call", "Customer said 'band karo'.", "Negative", "Frustrated", "Bad", 5, "Customer explicitly demanded to stop calling.", "None"],
    ["call_29", "Machine or call screener answered", "Voicemail", "Voicemail recording prompt.", "Neutral", "Neutral", "OK", 1, "Voicemail answered call.", "None"],
    ["call_30", "Gave a real answer, then left before an ending", "No outcome: customer left first", "Customer said voice not clear.", "Neutral", "Confused", "Bad", 5, "Audio clarity issue reported by customer.", "None"],
    # Call 31 - 35
    ["call_31", "Left during the first line, said nothing", "No outcome: customer left first", "", "Neutral", "Disengaged", "Bad", 1, "Agent audio missing, call dropped.", "None"],
    ["call_32", "Heard nothing from the agent", "No outcome: customer left first", "", "Can't tell", "Neutral", "Bad", 1, "Zero agent audio.", "None"],
    ["call_33", "Call reached an ending", "Not interested", "Customer said 'nahi karenge, ho gaya hai'.", "Neutral", "Disengaged", "OK", 3, "Customer declined renewal.", "None"],
    ["call_34", "Gave a real answer, then left before an ending", "No outcome: customer left first", "", "Neutral", "Confused", "OK", 4, "Interrupted turn.", "None"],
    ["call_35", "Gave a real answer, then left before an ending", "No outcome: customer left first", "", "Neutral", "Disengaged", "OK", 3, "Customer dropped.", "None"],
    # Call 36 - 40
    ["call_36", "Said hello or a few words, then left", "No outcome: customer left first", "", "Neutral", "Disengaged", "OK", 1, "Brief greeting before drop.", "None"],
    ["call_37", "Machine or call screener answered", "Voicemail", "Voicemail system announcement.", "Neutral", "Neutral", "Good", 1, "Voicemail detected accurately.", "None"],
    ["call_38", "Machine or call screener answered", "Call screener or machine", "Call screener announcement.", "Neutral", "Neutral", "OK", 1, "Call screening system.", "None"],
    ["call_39", "Gave a real answer, then left before an ending", "Not interested", "Policy: corporate insurance with employer.", "Neutral", "Cooperative", "Good", 5, "Customer stated existing corporate cover.", "None"],
    ["call_40", "Call reached an ending", "Not interested", "Customer said 'nahi chahiye madam'.", "Negative", "Disengaged", "OK", 3, "Customer declined firmly.", "None"],
    # Call 41 - 50
    ["call_41", "Said hello or a few words, then left", "No outcome: customer left first", "", "Neutral", "Disengaged", "OK", 1, "Dropped after initial hello.", "None"],
    ["call_42", "Gave a real answer, then left before an ending", "Not interested", "Arun ji not at home.", "Neutral", "Neutral", "OK", 1, "Target contact unavailable.", "None"],
    ["call_43", "Left during the first line, said nothing", "No outcome: customer left first", "", "Neutral", "Disengaged", "Bad", 1, "Agent audio missing.", "None"],
    ["call_44", "Call reached an ending", "Not interested", "Customer repeated 'nahi nahi'.", "Neutral", "Disengaged", "OK", 5, "Polite decline.", "None"],
    ["call_45", "Said hello or a few words, then left", "No outcome: customer left first", "", "Neutral", "Confused", "OK", 3, "Customer asked who is speaking.", "None"],
    ["call_46", "Gave a real answer, then left before an ending", "Call later agreed", "Customer requested call later ('ghar me nahi rahe').", "Neutral", "Cooperative", "OK", 3, "Customer requested callback.", "None"],
    ["call_47", "Agent's first words came late (over 3 s)", "No outcome: customer left first", "", "Neutral", "Disengaged", "Bad", 1, "Agent speech delayed over 3s, no agent audio files.", "None"],
    ["call_48", "Said hello or a few words, then left", "No outcome: customer left first", "", "Neutral", "Neutral", "OK", 3, "Brief exchange before disconnect.", "None"],
    ["call_49", "Said hello or a few words, then left", "No outcome: customer left first", "Customer asked who is calling.", "Neutral", "Confused", "OK", 8, "Customer asked identity before drop.", "None"],
    ["call_50", "Call reached an ending", "Not interested", "Customer said 'nahi nahi lekar kahi'.", "Negative", "Disengaged", "OK", 5, "Customer declined repeatedly.", "None"],
]

REPLY_CHECK_CALLS = (
    "call_01", "call_02", "call_03", "call_04", "call_05",
    "call_06", "call_07", "call_08", "call_09", "call_10",
    "call_11", "call_12", "call_14", "call_15", "call_16",
    "call_17", "call_18", "call_19", "call_20", "call_21",
)
GOLDEN_HEADERS = [
    "Call",
    "What happened",
    "Correct outcome",
    "Facts the customer gave",
    "Sentiment",
    "Emotion",
    "Overall",
    "First thing wrong: line",
    "First thing wrong: what",
    "Never-rule broken",
]
REPLY_HEADERS = [
    "Call",
    "Customer last word (s)",
    "Agent first sound (s)",
    "Gap (s)",
    "Turn index",
    "Notes",
]


def _read_turn_manifest(folder: Path, filename: str) -> dict[str, dict]:
    manifest_path = folder / filename
    if not manifest_path.is_file():
        return {}

    turns = {}
    with manifest_path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"Invalid record in {manifest_path}")
            turn = item.get("turn")
            if turn is not None:
                turns[str(turn)] = item
    return turns


def _seconds(value, *, call_id: str, field: str) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{call_id} has invalid {field}: {value!r}") from exc
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"{call_id} has invalid {field}: {value!r}")
    return seconds


def _message_metadata(message: dict) -> dict:
    metadata = message.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _build_reply_rows(calls_dir: Path) -> list[list]:
    rows = []
    for call_id in REPLY_CHECK_CALLS:
        folder = calls_dir / call_id
        call_json = folder / "call.json"
        if not call_json.is_file():
            raise FileNotFoundError(f"Missing call data: {call_json}")

        with call_json.open("r", encoding="utf-8") as file:
            call_data = json.load(file)
        if not isinstance(call_data, dict):
            raise ValueError(f"Call data must be an object: {call_json}")

        messages = call_data.get("messages") or []
        if not isinstance(messages, list):
            raise ValueError(f"Call messages must be a list: {call_json}")

        user_manifest = _read_turn_manifest(folder, "manifest.jsonl")
        agent_manifest = _read_turn_manifest(folder, "agent_manifest.jsonl")
        pair = None
        for index in range(len(messages) - 1):
            user_message = messages[index]
            agent_message = messages[index + 1]
            if not isinstance(user_message, dict) or not isinstance(agent_message, dict):
                raise ValueError(f"Invalid message in {call_json}")
            if user_message.get("role") == "user" and agent_message.get("role") == "assistant":
                pair = (user_message, agent_message)
                break

        if pair is None:
            continue

        user_message, agent_message = pair
        user_metadata = _message_metadata(user_message)
        user_turn = user_metadata.get("turn")
        user_manifest_entry = user_manifest.get(str(user_turn), {})
        user_start = _seconds(user_message.get("t"), call_id=call_id, field="user timestamp")
        user_audio_duration = user_metadata.get("audio_s")
        if user_audio_duration is not None:
            customer_end = user_start + _seconds(
                user_audio_duration, call_id=call_id, field="customer audio duration"
            )
        elif user_manifest_entry.get("seconds") is not None:
            customer_end = _seconds(
                user_manifest_entry["seconds"], call_id=call_id, field="customer speech end"
            )
        else:
            customer_end = user_start

        agent_metadata = _message_metadata(agent_message)
        agent_turn = agent_metadata.get("turn")
        agent_manifest_entry = agent_manifest.get(str(agent_turn), {})
        agent_first_sound = agent_manifest_entry.get("at_s")
        if agent_first_sound is None:
            agent_first_sound = agent_message.get("t")
        agent_first_sound = _seconds(
            agent_first_sound, call_id=call_id, field="agent audio start"
        )

        turn_index = user_turn if user_turn is not None else index + 1
        gap = max(0.0, agent_first_sound - customer_end)
        rows.append(
            [
                call_id,
                round(customer_end, 2),
                round(agent_first_sound, 2),
                round(gap, 2),
                turn_index,
                "Customer speech end to agent audio start",
            ]
        )
    return rows


def _write_temp_csv(output_dir: Path, filename: str, headers: list, rows: list[list]) -> Path:
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{filename}.",
        suffix=".tmp",
        dir=output_dir,
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(rows)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    return Path(temp_path)


def main() -> None:
    repository_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Generate golden benchmark CSV files")
    parser.add_argument("--data-dir", type=Path, default=None, help="Tenant call artifact directory")
    parser.add_argument(
        "--tenant-id",
        default=os.getenv("TENANT_ID", "health_campaign"),
        help="Tenant used to locate the default artifact directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "data",
        help="Directory for generated benchmark CSV files",
    )
    args = parser.parse_args()

    artifact_root = Path(
        os.getenv("ARTIFACT_STORAGE_PATH")
        or repository_root / "backend" / "storage" / "artifacts"
    )
    calls_dir = (args.data_dir or artifact_root / args.tenant_id).resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    reply_rows = _build_reply_rows(calls_dir)
    golden_csv = output_dir / "golden_dataset.csv"
    reply_csv = output_dir / "reply_wait_check_20_calls.csv"
    temp_paths = []
    try:
        reply_temp = _write_temp_csv(output_dir, reply_csv.name, REPLY_HEADERS, reply_rows)
        temp_paths.append(reply_temp)
        golden_temp = _write_temp_csv(output_dir, golden_csv.name, GOLDEN_HEADERS, golden_rows)
        temp_paths.append(golden_temp)
        os.replace(reply_temp, reply_csv)
        temp_paths.remove(reply_temp)
        os.replace(golden_temp, golden_csv)
        temp_paths.remove(golden_temp)
    finally:
        for temp_path in temp_paths:
            if temp_path.exists():
                temp_path.unlink()

    print(f"Generated {len(golden_rows)} rows in {golden_csv}")
    print(f"Generated {len(reply_rows)} rows in {reply_csv}")


if __name__ == "__main__":
    main()
