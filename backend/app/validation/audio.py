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

    required = ["call.json", "recording.wav"]
    for req in required:
        if not (call_dir / req).exists():
            errors.append(f"Missing required file: {req}")

    call_json_path = call_dir / "call.json"
    if call_json_path.exists():
        try:
            with open(call_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                errors.append("call.json must contain a JSON object")
            elif (
                not isinstance(data.get("call_id"), str)
                or not data["call_id"].strip()
            ):
                errors.append("call.json must contain a non-empty call_id")
        except Exception as exc:
            errors.append(f"Corrupt call.json: {exc}")

    recording_path = call_dir / "recording.wav"
    if recording_path.exists():
        wav_result = validate_wav(recording_path)
        if not wav_result.is_valid:
            errors.append(f"Invalid recording.wav: {wav_result.error}")

    phone_answered = False
    log_path = call_dir / "call.log"
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
                phone_answered = "phone answered" in log_content
        except Exception as exc:
            errors.append(f"Error reading call.log: {exc}")

    user_wavs = [
        path
        for path in call_dir.rglob("turn_*_user.wav")
        if path.is_file() and not path.is_symlink()
    ]
    user_manifest_count = 0
    manifest_path = call_dir / "manifest.jsonl"
    if manifest_path.exists():
        user_manifest_count = _count_manifest_entries(manifest_path, errors)

    agent_manifest_path = call_dir / "agent_manifest.jsonl"
    has_agent_manifest = agent_manifest_path.exists()
    agent_wavs = [
        path
        for path in call_dir.rglob("turn_*_agent.wav")
        if path.is_file() and not path.is_symlink()
    ]
    agent_manifest_count = 0
    if has_agent_manifest:
        agent_manifest_count = _count_manifest_entries(agent_manifest_path, errors)

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


def _count_manifest_entries(path: Path, errors: list[str]) -> int:
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as manifest:
            for line_number, line in enumerate(manifest, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"Malformed manifest entry at line {line_number}")
                    continue
                if not isinstance(entry, dict):
                    errors.append(
                        f"Manifest entry at line {line_number} must be an object"
                    )
                    continue
                count += 1
    except OSError as exc:
        errors.append(f"Error reading {path.name}: {exc}")
    return count

