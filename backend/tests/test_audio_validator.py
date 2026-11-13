import wave
from pathlib import Path
import pytest

from app.validation.audio import WavValidationResult, validate_wav, validate_call_files


def create_test_wav(
    path: Path,
    channels: int = 1,
    sample_rate: int = 16000,
    sample_width: int = 2,
    num_frames: int = 16000,
    silent: bool = False,
):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        if silent:
            data = b"\x00" * (channels * sample_width * num_frames)
        else:
            # Simple alternating non-zero samples
            data = (b"\x10\x00" * channels) * num_frames
        w.writeframes(data)


def test_validate_wav_stereo_16k(tmp_path: Path):
    wav_path = tmp_path / "stereo_16k.wav"
    create_test_wav(wav_path, channels=2, sample_rate=16000, num_frames=32000, silent=False)

    result = validate_wav(wav_path)
    assert result.is_valid is True
    assert result.channels == 2
    assert result.sample_rate == 16000
    assert result.sample_width == 2
    assert result.duration_s == 2.0
    assert result.is_silent is False
    assert result.error is None


def test_validate_wav_mono_24k(tmp_path: Path):
    wav_path = tmp_path / "mono_24k.wav"
    create_test_wav(wav_path, channels=1, sample_rate=24000, num_frames=24000, silent=False)

    result = validate_wav(wav_path)
    assert result.is_valid is True
    assert result.channels == 1
    assert result.sample_rate == 24000
    assert result.duration_s == 1.0
    assert result.is_silent is False


def test_validate_wav_digital_silence(tmp_path: Path):
    wav_path = tmp_path / "silent.wav"
    create_test_wav(wav_path, channels=2, sample_rate=16000, num_frames=16000, silent=True)

    result = validate_wav(wav_path)
    assert result.is_valid is True
    assert result.is_silent is True


def test_validate_wav_corrupt_file(tmp_path: Path):
    corrupt_path = tmp_path / "corrupt.wav"
    corrupt_path.write_bytes(b"not a valid wav header file contents")

    result = validate_wav(corrupt_path)
    assert result.is_valid is False
    assert result.error is not None


def test_validate_call_files_valid_folder(tmp_path: Path):
    call_dir = tmp_path / "call_01"
    call_dir.mkdir()
    (call_dir / "recording.wav").touch()
    create_test_wav(call_dir / "recording.wav", channels=2, sample_rate=16000)
    (call_dir / "call.json").write_text(
        '{"call_id": "c1", "call_key": "k1", "started_at": "2026-11-01T10:00:00Z", '
        '"ended_at": "2026-11-01T10:01:00Z", "disposition": "completed", "end_reason": "ended"}',
        encoding="utf-8",
    )
    (call_dir / "call.log").write_text("info: phone answered\nbye", encoding="utf-8")
    (call_dir / "manifest.jsonl").write_text('{"turn": 0, "seconds": 1.0}\n{"turn": "tail", "seconds": 0.5}\n', encoding="utf-8")
    create_test_wav(call_dir / "turn_0_user.wav")
    create_test_wav(call_dir / "turn_tail_user.wav")

    res = validate_call_files(call_dir)
    assert res.is_valid is True
    assert res.has_agent_manifest is False
    assert res.user_wav_count == 2
    assert res.user_manifest_count == 2
    assert res.phone_answered is True

