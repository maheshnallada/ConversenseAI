import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.envelope import (
    ArtifactReference,
    Execution,
    InteractionEnvelope,
    InteractionEvent,
    InteractionStatus,
)
from app.storage.artifacts import ArtifactStore
from app.storage.orm import ArtifactRow
from app.validation.audio import (
    CallFilesValidationResult,
    validate_call_files,
    validate_wav,
)


def _parse_iso(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    cleaned = ts_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _classify_status(end_reason: str | None) -> InteractionStatus:
    if end_reason == "ended":
        return "completed"
    if end_reason == "dropped":
        return "abandoned"
    if end_reason == "not_answered":
        return "failed"
    return "unknown"


def _determine_artifact_type(filename: str) -> str:
    name = filename.lower()
    if name == "recording.wav":
        return "recording"
    if name == "call.json":
        return "call_json"
    if name == "call.log":
        return "call_log"
    if name == "manifest.jsonl":
        return "manifest_user"
    if name == "agent_manifest.jsonl":
        return "manifest_agent"
    if name.startswith("turn_") and name.endswith("_user.wav"):
        return "turn_user_wav"
    if name.startswith("turn_") and name.endswith("_agent.wav"):
        return "turn_agent_wav"
    return "other"


def map_call_folder(
    folder_path: Path | str,
    tenant_id: str,
    artifact_store: ArtifactStore,
) -> tuple[InteractionEnvelope, list[ArtifactRow], CallFilesValidationResult]:
    folder = Path(folder_path).resolve()
    validation = validate_call_files(folder)

    call_json_path = folder / "call.json"
    if not call_json_path.exists():
        raise FileNotFoundError(f"Missing call.json in {folder}")

    with open(call_json_path, "r", encoding="utf-8") as f:
        call_data: dict[str, Any] = json.load(f)

    call_id = call_data["call_id"]
    call_key = call_data.get("call_key")
    started_at = _parse_iso(call_data.get("started_at"))
    ended_at = _parse_iso(call_data.get("ended_at"))
    status = _classify_status(call_data.get("end_reason"))

    # Process artifacts
    envelope_artifacts: list[ArtifactReference] = []
    artifact_rows: list[ArtifactRow] = []
    now = datetime.now(timezone.utc)

    # Collect all files in folder
    all_files = sorted(folder.iterdir(), key=lambda p: p.name)
    for file_path in all_files:
        if file_path.is_dir():
            continue

        artifact_type = _determine_artifact_type(file_path.name)
        stored = artifact_store.put_file(
            file_path,
            relative_dest=f"{tenant_id}/{folder.name}/{file_path.name}",
        )

        validation_status = "valid"
        validation_details: dict[str, Any] = {}

        if file_path.name.lower().endswith(".wav"):
            wav_val = validate_wav(file_path)
            validation_details = {
                "channels": wav_val.channels,
                "sample_rate": wav_val.sample_rate,
                "sample_width": wav_val.sample_width,
                "duration_s": wav_val.duration_s,
                "is_silent": wav_val.is_silent,
            }
            if not wav_val.is_valid:
                validation_status = "error"
                validation_details["error"] = wav_val.error
            elif wav_val.is_silent:
                validation_status = "silent"

        envelope_artifacts.append(
            ArtifactReference(
                artifact_id=stored.artifact_id,
                artifact_type=artifact_type,
                uri=stored.uri,
                media_type=stored.media_type,
                sha256=stored.sha256,
            )
        )

        artifact_rows.append(
            ArtifactRow(
                tenant_id=tenant_id,
                interaction_id=call_id,
                artifact_id=stored.artifact_id,
                artifact_type=artifact_type,
                uri=stored.uri,
                media_type=stored.media_type,
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                source_path=stored.source_path,
                validation_status=validation_status,
                validation_details_json=json.dumps(validation_details) if validation_details else None,
                created_at=now,
            )
        )

    # Build Execution
    models = call_data.get("models") or {}
    meta = call_data.get("meta") or {}
    usage = meta.get("usage") or {}
    llm_usage = usage.get("llm") or {}

    input_tokens = llm_usage.get("total_input_tokens") or llm_usage.get("estimated_input_tokens")
    output_tokens = llm_usage.get("total_output_tokens") or llm_usage.get("estimated_output_tokens")

    execution = Execution(
        provider=models.get("provider"),
        model=models.get("model"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=None,
        cost=None,
        currency="USD",
    )

    # Build Events
    events: list[InteractionEvent] = []
    messages = call_data.get("messages") or []
    for idx, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        meta_msg = msg.get("metadata") or {}
        events.append(
            InteractionEvent(
                event_id=f"msg_{idx}",
                event_type=f"message.{role}",
                occurred_at=None,
                payload={
                    "index": idx,
                    "role": role,
                    "content": msg.get("content"),
                    "t": msg.get("t"),
                    "metadata": meta_msg,
                },
            )
        )

    # Domain Data
    domain_data = {
        "disposition": call_data.get("disposition"),
        "end_reason": call_data.get("end_reason"),
        "to_number": call_data.get("to_number"),
        "channel": call_data.get("channel"),
        "environment": call_data.get("environment"),
        "room": call_data.get("room"),
        "folder_name": folder.name,
        "phone_answered": validation.phone_answered,
        "models": models,
        "meta": meta,
    }

    observability = {
        "latency": call_data.get("latency"),
        "usage": usage,
        "barges_count": len(call_data.get("barges") or []),
        "turns_count": len(call_data.get("turns") or []),
        "messages_count": len(messages),
    }

    participants = [
        {"role": "agent", "name": models.get("agent", "PolicyGuru Health Consultant")},
        {"role": "customer", "phone": call_data.get("to_number")},
    ]

    envelope = InteractionEnvelope(
        tenant_id=tenant_id,
        interaction_id=call_id,
        session_id=call_key,
        use_case="health_insurance",
        interaction_type="voice",
        schema_version="1.0",
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        correlation_id=folder.name,
        trace_id=call_data.get("room"),
        participants=participants,
        events=events,
        artifacts=envelope_artifacts,
        execution=execution,
        observability=observability,
        domain_data=domain_data,
        evaluation_refs=None,
    )

    return envelope, artifact_rows, validation

