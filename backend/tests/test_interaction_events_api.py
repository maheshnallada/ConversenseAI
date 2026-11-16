import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.app import create_app
from app.storage.transcript_repo import TranscriptRepository


def _client(session_factory):
    return TestClient(create_app(session_factory))


def _create_interaction(client, tenant_id, interaction_id):
    response = client.post(
        "/api/v1/interactions",
        headers={"X-Tenant-Id": tenant_id},
        json={
            "tenant_id": tenant_id,
            "interaction_id": interaction_id,
            "schema_version": "1.0",
        },
    )
    assert response.status_code == 201


def _event(event_id="event-1", event_type="transcript.turn", payload=None):
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": "2026-11-14T10:00:00Z",
        "payload": payload
        if payload is not None
        else {
            "turn_id": "turn-1",
            "turn_index": 7,
            "speaker": "customer",
            "raw_text": "నాకు policy కావాలి.",
            "playback_spoken": "heard",
            "playback_heard_text": "నాకు policy కావాలి.",
            "start_s": 1.25,
            "end_s": 2.75,
            "duration_s": 1.5,
            "audio_s": 1.4,
            "barged_in": False,
            "metadata": {"source": "asr", "confidence": 0.96},
        },
    }


def test_transcript_turn_event_maps_fields_without_changing_original_text(
    session_factory,
):
    client = _client(session_factory)
    _create_interaction(client, "tenant-a", "call-1")

    response = client.post(
        "/api/v1/interactions/call-1/events",
        headers={"X-Tenant-Id": "tenant-a"},
        json=_event(),
    )

    assert response.status_code == 201
    assert response.json()["created"] is True
    turns = TranscriptRepository(session_factory).get_turns("tenant-a", "call-1")
    assert len(turns) == 1
    assert turns[0].turn_index == 7
    assert turns[0].speaker == "customer"
    assert turns[0].raw_text == "నాకు policy కావాలి."
    assert turns[0].normalized_text == "నాకు policy కావాలి."
    assert turns[0].playback_spoken == "heard"
    assert turns[0].playback_heard_text == "నాకు policy కావాలి."
    assert turns[0].start_s == 1.25
    assert turns[0].end_s == 2.75
    assert turns[0].duration_s == 1.5
    assert turns[0].audio_s == 1.4
    assert turns[0].barged_in is False
    assert turns[0].metadata == {"source": "asr", "confidence": 0.96}
    with session_factory() as session:
        row = session.execute(
            text(
                "SELECT event_type, occurred_at FROM interaction_events "
                "WHERE tenant_id = 'tenant-a' AND event_id = 'event-1'"
            )
        ).one()
    assert row.event_type == "transcript.turn"
    assert datetime.fromisoformat(row.occurred_at) == datetime(2026, 11, 14, 10)


def test_missing_transcript_speaker_is_stored_as_unknown(session_factory):
    client = _client(session_factory)
    _create_interaction(client, "tenant-a", "call-1")
    event = _event(
        payload={
            "turn_id": "turn-1",
            "turn_index": 1,
            "raw_text": "Original line.",
        }
    )

    response = client.post(
        "/api/v1/interactions/call-1/events",
        headers={"X-Tenant-Id": "tenant-a"},
        json=event,
    )

    assert response.status_code == 201
    turns = TranscriptRepository(session_factory).get_turns("tenant-a", "call-1")
    assert turns[0].speaker == "unknown"
    assert turns[0].raw_text == "Original line."


def test_appending_turn_event_preserves_previously_saved_turns(session_factory):
    client = _client(session_factory)
    _create_interaction(client, "tenant-a", "call-1")
    headers = {"X-Tenant-Id": "tenant-a"}

    first = client.post(
        "/api/v1/interactions/call-1/events",
        headers=headers,
        json=_event(
            event_id="event-1",
            payload={
                "turn_id": "turn-1",
                "turn_index": 0,
                "speaker": "agent",
                "raw_text": "First line.",
            },
        ),
    )
    second = client.post(
        "/api/v1/interactions/call-1/events",
        headers=headers,
        json=_event(
            event_id="event-2",
            payload={
                "turn_id": "turn-2",
                "turn_index": 1,
                "speaker": "customer",
                "raw_text": "Second line.",
            },
        ),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    turns = TranscriptRepository(session_factory).get_turns("tenant-a", "call-1")
    assert [(turn.turn_index, turn.raw_text) for turn in turns] == [
        (0, "First line."),
        (1, "Second line."),
    ]


def test_identical_event_replay_is_idempotent(session_factory):
    client = _client(session_factory)
    _create_interaction(client, "tenant-a", "call-1")
    event = _event()
    url = "/api/v1/interactions/call-1/events"
    headers = {"X-Tenant-Id": "tenant-a"}

    first = client.post(url, headers=headers, json=event)
    replay = client.post(url, headers=headers, json=event)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    with session_factory() as session:
        count = session.scalar(
            text(
                "SELECT COUNT(*) FROM interaction_events "
                "WHERE tenant_id = 'tenant-a' AND interaction_id = 'call-1' "
                "AND event_id = 'event-1'"
            )
        )
    assert count == 1
    assert len(TranscriptRepository(session_factory).get_turns("tenant-a", "call-1")) == 1


def test_conflicting_event_replay_returns_conflict(session_factory):
    client = _client(session_factory)
    _create_interaction(client, "tenant-a", "call-1")
    url = "/api/v1/interactions/call-1/events"
    headers = {"X-Tenant-Id": "tenant-a"}

    first = client.post(url, headers=headers, json=_event())
    changed = _event(
        payload={
            "turn_id": "turn-1",
            "turn_index": 7,
            "speaker": "customer",
            "raw_text": "Changed text.",
        }
    )
    conflict = client.post(url, headers=headers, json=changed)

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert len(TranscriptRepository(session_factory).get_turns("tenant-a", "call-1")) == 1


def test_unknown_event_type_is_preserved(session_factory):
    client = _client(session_factory)
    _create_interaction(client, "tenant-a", "call-1")
    event = _event(
        event_id="vendor-event",
        event_type="vendor.custom.event",
        payload={"state": "opaque", "value": 7},
    )

    response = client.post(
        "/api/v1/interactions/call-1/events",
        headers={"X-Tenant-Id": "tenant-a"},
        json=event,
    )

    assert response.status_code == 201
    with session_factory() as session:
        row = session.execute(
            text(
                "SELECT event_type, payload_json FROM interaction_events "
                "WHERE tenant_id = 'tenant-a' AND event_id = 'vendor-event'"
            )
        ).one()
    assert row.event_type == "vendor.custom.event"
    assert json.loads(row.payload_json) == event["payload"]
    assert TranscriptRepository(session_factory).get_turns("tenant-a", "call-1") == []


def test_event_registration_requires_existing_tenant_scoped_interaction(
    session_factory,
):
    client = _client(session_factory)
    _create_interaction(client, "tenant-a", "call-1")
    url = "/api/v1/interactions/call-1/events"
    event = _event()

    missing_interaction = client.post(
        "/api/v1/interactions/missing/events",
        headers={"X-Tenant-Id": "tenant-a"},
        json=event,
    )
    other_tenant = client.post(
        url,
        headers={"X-Tenant-Id": "tenant-b"},
        json=event,
    )
    missing_tenant = client.post(url, json=event)

    assert missing_interaction.status_code == 404
    assert other_tenant.status_code == 404
    assert missing_tenant.status_code == 401
