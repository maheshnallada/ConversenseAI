import io
import json
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.app import create_app
from app.storage.artifacts import LocalArtifactStore
from app.storage.orm import EvaluationRunRow, InteractionRow


def wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b"\x01\x00" * 1600)
    return buffer.getvalue()


def create_staged_folder(
    store: LocalArtifactStore,
    tenant_id: str,
    folder_name: str,
    call_id: str,
    include_recording: bool = True,
) -> Path:
    folder = store.base_dir / tenant_id / folder_name
    folder.mkdir(parents=True)
    (folder / "call.json").write_text(
        json.dumps({"call_id": call_id, "messages": []}),
        encoding="utf-8",
    )
    if include_recording:
        (folder / "recording.wav").write_bytes(wav_bytes())
    return folder


def create_client(session_factory, artifact_root: Path):
    store = LocalArtifactStore(artifact_root)
    return TestClient(create_app(session_factory, artifact_store=store)), store


def test_staged_call_listing_shows_ready_and_incomplete_calls_without_paths(
    tmp_path: Path,
    session_factory,
):
    client, store = create_client(session_factory, tmp_path / "artifacts")
    create_staged_folder(store, "tenant-a", "ready-call", "ready-id")
    create_staged_folder(
        store,
        "tenant-a",
        "incomplete-call",
        "incomplete-id",
        include_recording=False,
    )

    response = client.get(
        "/api/v1/imports/staged-calls",
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert response.status_code == 200
    calls = {call["display_name"]: call for call in response.json()["calls"]}
    assert calls["ready-call"]["is_ready"] is True
    assert calls["ready-call"]["validation_errors"] == []
    assert calls["incomplete-call"]["is_ready"] is False
    assert "Missing required file: recording.wav" in calls["incomplete-call"][
        "validation_errors"
    ]
    assert str(store.base_dir) not in response.text
    assert all("folder_id" in call for call in calls.values())


def test_staged_import_is_tenant_scoped_and_reports_partial_results_without_evaluation(
    tmp_path: Path,
    session_factory,
    monkeypatch,
):
    from app.evaluation.service import EvaluationService

    client, store = create_client(session_factory, tmp_path / "artifacts")
    create_staged_folder(store, "tenant-a", "ready-call", "ready-id")
    create_staged_folder(
        store,
        "tenant-a",
        "incomplete-call",
        "incomplete-id",
        include_recording=False,
    )
    listing = client.get(
        "/api/v1/imports/staged-calls",
        headers={"X-Tenant-Id": "tenant-a"},
    ).json()["calls"]

    def fail_if_evaluated(*args, **kwargs):
        raise AssertionError("call import must not trigger evaluation")

    monkeypatch.setattr(EvaluationService, "evaluate_interaction", fail_if_evaluated)
    response = client.post(
        "/api/v1/imports/staged-calls",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"folder_ids": [call["folder_id"] for call in listing]},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["total_calls"] == 2
    assert result["created"] == 1
    assert result["replayed"] == 0
    assert result["failed"] == 1
    assert {call["status"] for call in result["calls"]} == {"created", "invalid"}
    ready_result = next(
        call for call in result["calls"] if call["folder_name"] == "ready-call"
    )
    assert ready_result["audio_validation"]["is_valid"] is True
    assert str(store.base_dir) not in response.text

    other_tenant_listing = client.get(
        "/api/v1/imports/staged-calls",
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert other_tenant_listing.status_code == 200
    assert other_tenant_listing.json()["calls"] == []
    guessed_id = client.post(
        "/api/v1/imports/staged-calls",
        headers={"X-Tenant-Id": "tenant-b"},
        json={"folder_ids": [listing[0]["folder_id"]]},
    )
    assert guessed_id.status_code == 404
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InteractionRow)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationRunRow)) == 0


def test_single_uploaded_call_folder_is_imported(tmp_path: Path, session_factory):
    client, store = create_client(session_factory, tmp_path / "artifacts")
    response = client.post(
        "/api/v1/imports/upload-calls",
        headers={"X-Tenant-Id": "tenant-a"},
        files=[
            ("files", ("call.json", b'{"call_id":"single-call","messages":[]}', "application/json")),
            ("files", ("recording.wav", wav_bytes(), "audio/wav")),
        ],
    )

    assert response.status_code == 200
    result = response.json()
    assert result["total_calls"] == 1
    assert result["created"] == 1
    assert result["calls"][0]["folder_name"] == "Uploaded call"
    assert result["calls"][0]["interaction_id"] == "single-call"
    assert str(store.base_dir) not in response.text


def test_uploaded_batch_preserves_success_when_another_call_is_invalid(
    tmp_path: Path,
    session_factory,
):
    client, store = create_client(session_factory, tmp_path / "artifacts")
    response = client.post(
        "/api/v1/imports/upload-calls",
        headers={"X-Tenant-Id": "tenant-a"},
        files=[
            (
                "files",
                ("batch/valid/call.json", b'{"call_id":"valid-call","messages":[]}', "application/json"),
            ),
            ("files", ("batch/valid/recording.wav", wav_bytes(), "audio/wav")),
            ("files", ("batch/incomplete/recording.wav", wav_bytes(), "audio/wav")),
        ],
    )

    assert response.status_code == 200
    result = response.json()
    assert result["total_calls"] == 2
    assert result["created"] == 1
    assert result["failed"] == 1
    assert {call["status"] for call in result["calls"]} == {"created", "invalid"}
    assert {call["folder_name"] for call in result["calls"]} == {
        "valid",
        "incomplete",
    }
    assert str(store.base_dir) not in response.text


@pytest.mark.parametrize(
    "filename",
    [
        "../outside/call.json",
        "/outside/call.json",
    ],
)
def test_upload_rejects_traversal_and_rooted_paths_before_persistence(
    tmp_path: Path,
    session_factory,
    filename: str,
):
    client, _ = create_client(session_factory, tmp_path / "artifacts")
    boundary = "import-test-boundary"
    parts = [
        (
            filename,
            b'{"call_id":"unsafe-call"}',
            "application/json",
        ),
        ("recording.wav", wav_bytes(), "audio/wav"),
    ]
    body = b"".join(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        + content
        + b"\r\n"
        for name, content, content_type in parts
    ) + f"--{boundary}--\r\n".encode("ascii")
    response = client.post(
        "/api/v1/imports/upload-calls",
        headers={
            "X-Tenant-Id": "tenant-a",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        content=body,
    )

    assert response.status_code == 400
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InteractionRow)) == 0


def test_upload_does_not_use_windows_drive_path_as_storage_path(
    tmp_path: Path,
    session_factory,
):
    client, store = create_client(session_factory, tmp_path / "artifacts")
    filename = "C:\\outside\\call.json"
    boundary = "import-test-boundary"
    parts = [
        (filename, b'{"call_id":"safe-basename","messages":[]}', "application/json"),
        ("recording.wav", wav_bytes(), "audio/wav"),
    ]
    body = b"".join(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        + content
        + b"\r\n"
        for name, content, content_type in parts
    ) + f"--{boundary}--\r\n".encode("ascii")

    response = client.post(
        "/api/v1/imports/upload-calls",
        headers={
            "X-Tenant-Id": "tenant-a",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        content=body,
    )

    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert response.json()["calls"][0]["interaction_id"] == "safe-basename"
    assert str(store.base_dir) not in response.text
    assert not (tmp_path / "outside" / "call.json").exists()


def test_upload_rejects_duplicate_normalized_relative_paths(
    tmp_path: Path,
    session_factory,
):
    client, _ = create_client(session_factory, tmp_path / "artifacts")
    response = client.post(
        "/api/v1/imports/upload-calls",
        headers={"X-Tenant-Id": "tenant-a"},
        files=[
            ("files", ("batch/call/call.json", b'{"call_id":"duplicate"}', "application/json")),
            ("files", ("batch\\call\\call.json", b'{"call_id":"duplicate"}', "application/json")),
            ("files", ("batch/call/recording.wav", wav_bytes(), "audio/wav")),
        ],
    )

    assert response.status_code == 400
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InteractionRow)) == 0


def test_staged_import_rejects_symlink_before_persisting(
    tmp_path: Path,
    session_factory,
):
    client, store = create_client(session_factory, tmp_path / "artifacts")
    folder = create_staged_folder(store, "tenant-a", "unsafe-call", "unsafe-id")
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    try:
        (folder / "linked.txt").symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation is not available in this environment")
    folder_id = client.get(
        "/api/v1/imports/staged-calls",
        headers={"X-Tenant-Id": "tenant-a"},
    ).json()["calls"][0]["folder_id"]

    response = client.post(
        "/api/v1/imports/staged-calls",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"folder_ids": [folder_id]},
    )

    assert response.status_code == 400
    assert str(store.base_dir) not in response.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InteractionRow)) == 0


def test_upload_import_limits_enforce_all_approved_boundaries():
    from app.api.app import _validate_import_limits

    mebibyte = 1024 * 1024
    _validate_import_limits([[1]] * 100)
    _validate_import_limits([[1] * 200])
    _validate_import_limits([[1] * 100] * 100)
    _validate_import_limits([[512 * mebibyte]])
    _validate_import_limits([[512 * mebibyte] * 10])

    invalid_sizes = [
        [[1]] * 101,
        [[1] * 201],
        [[1] * 100] * 99 + [[1] * 101],
        [[512 * mebibyte + 1]],
        [[512 * mebibyte] * 11],
    ]
    for file_sizes_by_call in invalid_sizes:
        with pytest.raises(HTTPException) as exc_info:
            _validate_import_limits(file_sizes_by_call)
        assert exc_info.value.status_code == 413


def test_upload_accepts_more_than_default_multipart_file_limit(
    tmp_path: Path,
    session_factory,
):
    client, _ = create_client(session_factory, tmp_path / "artifacts")
    uploads = []
    call_count = 6
    file_index = 0
    for call_number in range(call_count):
        prefix = f"batch/call-{call_number}/"
        uploads.extend(
            [
                (
                    "files",
                    (
                        f"{prefix}call.json",
                        json.dumps(
                            {
                                "call_id": f"many-files-{call_number}",
                                "messages": [],
                            }
                        ).encode("utf-8"),
                        "application/json",
                    ),
                ),
                ("files", (f"{prefix}recording.wav", wav_bytes(), "audio/wav")),
            ]
        )
        file_index += 2
    while file_index < 1001:
        call_number = file_index % call_count
        uploads.append(
            (
                "files",
                (
                    f"batch/call-{call_number}/extra-{file_index}.txt",
                    b"extra",
                    "text/plain",
                ),
            )
        )
        file_index += 1

    response = client.post(
        "/api/v1/imports/upload-calls",
        headers={"X-Tenant-Id": "tenant-a"},
        files=uploads,
    )

    assert response.status_code == 200
    assert response.json()["total_calls"] == call_count
    assert response.json()["created"] == call_count
