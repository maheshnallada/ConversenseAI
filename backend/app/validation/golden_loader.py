from pathlib import Path
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

from app.domain.envelope import InteractionEnvelope, InteractionEvent
from app.domain.golden import (
    GoldenCallLabel,
    GoldenDataset,
    GoldenDatasetRecord,
    GoldenEvaluationInput,
)
from app.domain.transcript import TranscriptTurn
from app.evaluation.schemas import ConversationStatus
from app.reconstruction.processor import TranscriptProcessor

REQUIRED_HEADERS = {
    "call_id",
    "model_input_json_excluding_saved_outcome",
    "gold_correct_outcome",
    "gold_sentiment",
    "gold_emotion",
    "gold_overall",
    "gold_never-rule_broken",
}


def _parse_test_flag(raw_value: Any) -> bool | None:
    value = str(raw_value or "").strip()
    if value == "":
        return None
    lowered = value.lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    if lowered in {"unknown", "unk", "unavailable", "?"}:
        return None
    return None


def _make_input_hash(model_input: Any, user_manifest: dict[str, Any], agent_manifest: dict[str, Any]) -> str:
    payload = {
        "model_input": model_input,
        "manifest": user_manifest,
        "agent_manifest": agent_manifest,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_jsonl(raw_value: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    if raw_value is None or str(raw_value).strip() == "":
        return manifest
    for line in str(raw_value).splitlines():
        line_text = line.strip()
        if not line_text:
            continue
        try:
            item = json.loads(line_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed manifest JSON: {exc}") from exc
        if isinstance(item, dict):
            turn_key = str(item.get("turn"))
            manifest[turn_key] = item
    return manifest


def _validate_csv_row_structure(row: dict[str, Any] | None, row_number: int) -> None:
    if row is None or None in row or any(value is None for value in row.values()):
        raise ValueError(f"Malformed CSV row structure at row {row_number}: missing or extra fields.")


def _build_envelope(call_id: str, tenant_id: str, call_data: dict[str, Any]) -> InteractionEnvelope:
    meta = call_data.get("meta") if isinstance(call_data.get("meta"), dict) else {}
    started_at = _parse_iso_datetime(call_data.get("started_at"))
    ended_at = _parse_iso_datetime(call_data.get("ended_at"))
    session_id_value = call_data.get("call_key") or call_data.get("session_id")
    interaction_status = call_data.get("status") or call_data.get("final_state") or call_data.get("state") or None
    envelope = InteractionEnvelope(
        tenant_id=tenant_id,
        interaction_id=call_id,
        session_id=str(session_id_value) if session_id_value is not None else None,
        schema_version="1.0",
        status=interaction_status,
        started_at=started_at,
        ended_at=ended_at,
        domain_data={
            "meta": meta,
            "channel": call_data.get("channel"),
            "environment": call_data.get("environment"),
            "end_reason": call_data.get("end_reason"),
        },
        observability={"source_call_id": call_data.get("call_id")},
        participants=[{"role": "customer", "id": meta.get("to_number")}] if meta.get("to_number") else None,
    )
    return envelope


def _build_events(call_id: str, call_data: dict[str, Any]) -> list[InteractionEvent]:
    events: list[InteractionEvent] = []
    for idx, item in enumerate(call_data.get("messages") or []):
        content = item.get("content") or ""
        event = InteractionEvent(
            event_id=f"{call_id}_msg_{idx}",
            event_type=item.get("role", "unknown"),
            occurred_at=_parse_iso_datetime(item.get("t")),
            payload={
                "role": item.get("role"),
                "content": content,
                "metadata": item.get("metadata"),
            },
        )
        if item.get("t") is not None:
            event.occurred_at = _parse_iso_datetime(item.get("t"))
        events.append(event)
    return events


def load_golden_dataset(csv_path: Path | str, tenant_id: str = "tenant_default") -> GoldenDataset:
    """
    Parses the CSV of golden dataset input records into canonical model inputs and reusable labels.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset CSV not found: {path}")

    previous_limit = csv.field_size_limit()
    csv.field_size_limit(2_000_000)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames or []
            missing_headers = sorted(REQUIRED_HEADERS - set(fieldnames))
            if not fieldnames or missing_headers:
                raise ValueError(f"Missing required golden dataset headers: {missing_headers}")

            seen_call_ids: set[str] = set()
            records: list[GoldenDatasetRecord] = []
            for row in reader:
                _validate_csv_row_structure(row, reader.line_num)
                raw_call_id = str(row.get("call_id") or "").strip()
                if raw_call_id:
                    if raw_call_id in seen_call_ids:
                        raise ValueError(f"Duplicate call_id in golden dataset: {raw_call_id!r}")
                    seen_call_ids.add(raw_call_id)

                conversation_status = (row.get("conversation_status") or row.get("Conversation status") or "").strip() or None
                language_slice = (row.get("language_slice") or row.get("Language slice") or "").strip() or None
                if conversation_status is not None and conversation_status not in get_args(ConversationStatus):
                    raise ValueError(f"Conversation status {conversation_status!r} is invalid for call {raw_call_id!r}.")
                label = GoldenCallLabel(
                    call_id=raw_call_id,
                    what_happened=str(row.get("gold_what_happened") or row.get("What happened") or "").strip(),
                    correct_outcome=str(row.get("gold_correct_outcome") or row.get("Correct outcome") or "").strip(),
                    facts_customer_gave=str(row.get("gold_facts_the_customer_gave") or row.get("Facts the customer gave") or "").strip(),
                    sentiment=str(row.get("gold_sentiment") or row.get("Sentiment") or "").strip() or "Neutral",
                    emotion=str(row.get("gold_emotion") or row.get("Emotion") or "").strip() or "Neutral",
                    overall=str(row.get("gold_overall") or row.get("Overall") or "").strip() or "Good",
                    first_thing_wrong_line=(
                        int(value) if (value := str(row.get("gold_first_thing_wrong_line") or row.get("First thing wrong: line") or "").strip()) and value.isdigit() else None
                    ),
                    first_thing_wrong_what=str(row.get("gold_first_thing_wrong_what") or row.get("First thing wrong: what") or "").strip() or None,
                    never_rule_broken=str(row.get("gold_never-rule_broken") or row.get("Never-rule broken") or "").strip() or "None",
                    reviewer_notes=(row.get("gold_human_review_notes") or "").strip() or None,
                    conversation_status=conversation_status,
                    language_slice=language_slice,
                )
                record = GoldenDatasetRecord(label=label, test_flag=_parse_test_flag(row.get("gold_test_flag")))

                raw_input = (row.get("model_input_json_excluding_saved_outcome") or "").strip()
                if not raw_input:
                    record.error = "Missing model input JSON for golden record."
                    records.append(record)
                    continue
                try:
                    model_input = json.loads(raw_input)
                    if not isinstance(model_input, dict):
                        raise TypeError("model input must decode to an object")
                    user_manifest = _load_jsonl(row.get("manifest_jsonl"))
                    agent_manifest = _load_jsonl(row.get("agent_manifest_jsonl"))
                    embedded_call_id = str(model_input.get("call_id") or "").strip()
                    if raw_call_id and embedded_call_id and embedded_call_id != raw_call_id:
                        raise ValueError(f"Embedded call_id {embedded_call_id!r} does not match outer call_id {raw_call_id!r}.")
                    if not embedded_call_id and raw_call_id:
                        model_input["call_id"] = raw_call_id
                    input_hash = _make_input_hash(model_input, user_manifest, agent_manifest)
                    record.input_hash = input_hash

                    interaction = _build_envelope(raw_call_id or embedded_call_id, tenant_id, model_input)
                    interaction.events = _build_events(interaction.interaction_id, model_input)
                    turns = TranscriptProcessor().process_call_data(model_input, tenant_id, user_manifest, agent_manifest)
                    record.evaluation_input = GoldenEvaluationInput(interaction=interaction, turns=turns)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    record.error = str(exc)

                records.append(record)

            dataset_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            return GoldenDataset(dataset_hash=dataset_hash, records=records)
    finally:
        csv.field_size_limit(previous_limit)


def load_reply_wait_checks(csv_path: Path | str) -> list[dict[str, Any]]:
    """
    Parses the 20-call reply wait check CSV.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Reply wait check CSV not found: {path}")

    checks: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            checks.append({
                "call_id": row.get("Call", "").strip(),
                "customer_last_word_s": float(row.get("Customer last word (s)", 0.0)),
                "agent_first_sound_s": float(row.get("Agent first sound (s)", 0.0)),
                "gap_s": float(row.get("Gap (s)", 0.0)),
                "turn_index": int(row.get("Turn index")) if row.get("Turn index") else None,
                "notes": row.get("Notes", "").strip(),
            })

    return checks
