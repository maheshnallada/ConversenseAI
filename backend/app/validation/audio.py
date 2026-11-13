import json
import wave
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WavValidationResult:
    is_valid: bool
    channels: int | None = None
    sample_rate: int | None = None
    sample_width: int | None = None
    frames: int | None = None
    duration_s: float | None = None
    is_silent: bool = False
    error: str | None = None


def validate_wav(path: Path | str) -> WavValidationResult:
    p = Path(path)
    if not p.exists():
        return WavValidationResult(is_valid=False, error=f"File not found: {p}")

    try:
        with wave.open(str(p), "rb") as w:
            channels = w.getnchannels()
            sample_rate = w.getframerate()
            sample_width = w.getsampwidth()
            frames = w.getnframes()
            duration_s = round(frames / float(sample_rate), 4) if sample_rate > 0 else 0.0

            # Check for digital silence (peak amplitude is 0)
            is_silent = True
            chunk_size = 8192
            remaining = frames
            while remaining > 0:
                read_count = min(chunk_size, remaining)
                data = w.readframes(read_count)
                if not data:
                    break
                remaining -= read_count
                # If any non-zero byte exists, audio has energy
                if any(b != 0 for b in data):
                    is_silent = False
                    break

            return WavValidationResult(
                is_valid=True,
                channels=channels,
                sample_rate=sample_rate,
                sample_width=sample_width,
                frames=frames,
                duration_s=duration_s,
                is_silent=is_silent,
            )
    except Exception as exc:
        return WavValidationResult(is_valid=False, error=str(exc))


@dataclass
class CallFilesValidationResult:
    is_valid: bool
    has_agent_manifest: bool
    user_wav_count: int
    user_manifest_count: int
    agent_wav_count: int
    agent_manifest_count: int
    phone_answered: bool
    errors: list[str] = field(default_factory=list)


def validate_call_files(folder: Path | str) -> CallFilesValidationResult:
    call_dir = Path(folder)
    errors: list[str] = []

    # Required files
    required = ["recording.wav", "call.json", "call.log", "manifest.jsonl"]
    for req in required:
        if not (call_dir / req).exists():
            errors.append(f"Missing required file: {req}")

    # Inspect call.json
    call_json_path = call_dir / "call.json"
    if call_json_path.exists():
        try:
            with open(call_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in ["call_id", "call_key", "started_at", "ended_at", "disposition", "end_reason"]:
                if key not in data:
                    errors.append(f"Missing required key in call.json: {key}")
        except Exception as exc:
            errors.append(f"Corrupt call.json: {exc}")

    # Inspect call.log
    phone_answered = False
    log_path = call_dir / "call.log"
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
                phone_answered = "phone answered" in log_content
        except Exception as exc:
            errors.append(f"Error reading call.log: {exc}")

    # Inspect user manifest and WAVs
    user_wavs = list(call_dir.glob("turn_*_user.wav"))
    user_manifest_count = 0
    manifest_path = call_dir / "manifest.jsonl"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [line.strip() for line in f if line.strip()]
                user_manifest_count = len(lines)
        except Exception as exc:
            errors.append(f"Error reading manifest.jsonl: {exc}")

    if manifest_path.exists() and len(user_wavs) != user_manifest_count:
        errors.append(f"User WAV count ({len(user_wavs)}) does not match manifest count ({user_manifest_count})")

    # Inspect agent manifest and WAVs (optional)
    agent_manifest_path = call_dir / "agent_manifest.jsonl"
    has_agent_manifest = agent_manifest_path.exists()
    agent_wavs = list(call_dir.glob("turn_*_agent.wav"))
    agent_manifest_count = 0
    if has_agent_manifest:
        try:
            with open(agent_manifest_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [line.strip() for line in f if line.strip()]
                agent_manifest_count = len(lines)
        except Exception as exc:
            errors.append(f"Error reading agent_manifest.jsonl: {exc}")

        if len(agent_wavs) != agent_manifest_count:
            errors.append(f"Agent WAV count ({len(agent_wavs)}) does not match manifest count ({agent_manifest_count})")

    is_valid = len(errors) == 0
    return CallFilesValidationResult(
        is_valid=is_valid,
        has_agent_manifest=has_agent_manifest,
        user_wav_count=len(user_wavs),
        user_manifest_count=user_manifest_count,
        agent_wav_count=len(agent_wavs),
        agent_manifest_count=agent_manifest_count,
        phone_answered=phone_answered,
        errors=errors,
    )

