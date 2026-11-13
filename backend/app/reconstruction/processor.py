import json
from pathlib import Path
from typing import Any

from app.domain.transcript import TranscriptTurn
from app.reconstruction.normalizer import normalize_text


class TranscriptProcessor:
    def process_folder(
        self,
        call_folder: Path | str,
        tenant_id: str,
    ) -> list[TranscriptTurn]:
        folder = Path(call_folder).resolve()
        call_json_path = folder / "call.json"
        if not call_json_path.exists():
            raise FileNotFoundError(f"Missing call.json in {folder}")

        with open(call_json_path, "r", encoding="utf-8") as f:
            call_data: dict[str, Any] = json.load(f)

        call_id = call_data["call_id"]
        messages: list[dict[str, Any]] = call_data.get("messages") or []

        # Load user manifest
        user_manifest: dict[str, dict[str, Any]] = {}
        manifest_path = folder / "manifest.jsonl"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        turn_key = str(item.get("turn"))
                        user_manifest[turn_key] = item

        # Load agent manifest (if exists)
        agent_manifest: dict[str, dict[str, Any]] = {}
        agent_manifest_path = folder / "agent_manifest.jsonl"
        if agent_manifest_path.exists():
            with open(agent_manifest_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        turn_key = str(item.get("turn"))
                        agent_manifest[turn_key] = item

        turns: list[TranscriptTurn] = []

        for idx, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            speaker = "agent" if role == "assistant" else "customer" if role == "user" else "system"
            raw_text = msg.get("content") or ""
            norm_text = normalize_text(raw_text)

            meta = msg.get("metadata") or {}
            t = msg.get("t")
            start_s = round(float(t), 3) if t is not None else None

            audio_s = meta.get("audio_s")
            duration_s = round(float(audio_s), 3) if audio_s is not None else None
            end_s = (
                round(start_s + duration_s, 3)
                if (start_s is not None and duration_s is not None)
                else None
            )

            # Playback metadata: None if absent (e.g. on studio calls)
            playback_spoken = meta.get("spoken")
            playback_heard = meta.get("heard")
            barged_in = meta.get("barged_in")

            extra_meta: dict[str, Any] = {
                "source": meta.get("source"),
                "turn": meta.get("turn"),
                "message_type": meta.get("message_type"),
                "endpoint_ms": meta.get("endpoint_ms"),
                "stt_ms": meta.get("stt_ms"),
                "tts_ms": meta.get("tts_ms"),
                "response_time": meta.get("response_time"),
            }

            turn_key = str(meta.get("turn")) if meta.get("turn") is not None else None
            if turn_key is not None:
                if speaker == "customer" and turn_key in user_manifest:
                    u_item = user_manifest[turn_key]
                    extra_meta["user_wav"] = u_item.get("user_wav")
                    extra_meta["manifest_transcript"] = u_item.get("transcript")
                    if duration_s is None and u_item.get("seconds"):
                        duration_s = round(float(u_item["seconds"]), 3)
                        if start_s is not None:
                            end_s = round(start_s + duration_s, 3)

                elif speaker == "agent" and turn_key in agent_manifest:
                    a_item = agent_manifest[turn_key]
                    extra_meta["agent_wav"] = a_item.get("agent_wav")
                    extra_meta["manifest_text"] = a_item.get("text")
                    extra_meta["at_s"] = a_item.get("at_s")
                    if duration_s is None and a_item.get("seconds"):
                        duration_s = round(float(a_item["seconds"]), 3)
                        if start_s is not None:
                            end_s = round(start_s + duration_s, 3)

            turn_id = f"{call_id}_turn_{idx}"
            turns.append(
                TranscriptTurn(
                    turn_id=turn_id,
                    interaction_id=call_id,
                    tenant_id=tenant_id,
                    turn_index=idx,
                    speaker=speaker,
                    raw_text=raw_text,
                    normalized_text=norm_text,
                    start_s=start_s,
                    end_s=end_s,
                    duration_s=duration_s,
                    playback_spoken=playback_spoken,
                    playback_heard_text=playback_heard,
                    audio_s=duration_s,
                    barged_in=barged_in,
                    metadata=extra_meta,
                )
            )

        return turns

