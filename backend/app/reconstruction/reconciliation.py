from collections import Counter
from dataclasses import dataclass
from typing import Literal

from app.domain.envelope import InteractionEvent
from app.domain.timeline import TimelineReconciliation
from app.domain.transcript import TranscriptTurn
from app.reconstruction.timing import is_valid_turn_timing

DeliveryStatus = Literal[
    "heard",
    "cut",
    "not_played",
    "no_audio",
    "unknown",
    "mismatch",
    "customer_turn",
    "system_turn",
]


@dataclass
class DeliveryClassification:
    status: DeliveryStatus
    is_agent: bool
    was_heard: bool | None
    was_cut: bool
    heard_text: str | None
    raw_text: str
    evidence_note: str
    turn_id: str | None = None
    turn_index: int | None = None
    requires_review: bool = False


def classify_delivery(turn: TranscriptTurn) -> DeliveryClassification:
    if turn.speaker != "agent":
        status = "customer_turn" if turn.speaker == "customer" else (
            "system_turn" if turn.speaker == "system" else "unknown"
        )
        return DeliveryClassification(
            status=status,
            is_agent=False,
            was_heard=None,
            was_cut=False,
            heard_text=None,
            raw_text=turn.raw_text,
            evidence_note=(
                "Customer turn; playback is not applicable"
                if turn.speaker == "customer"
                else "Non-agent speaker label"
            ),
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
            requires_review=False,
        )

    spoken = turn.playback_spoken
    heard_text = turn.playback_heard_text

    # Check for contradictory evidence
    if (
        spoken in {"not_played", "no_audio"}
        and heard_text
        and heard_text.strip()
    ) or (
        spoken == "cut"
        and heard_text
        and heard_text == turn.raw_text
        and bool(turn.raw_text)
    ):
        return DeliveryClassification(
            status="mismatch",
            is_agent=True,
            was_heard=None,
            was_cut=spoken == "cut",
            heard_text=heard_text,
            raw_text=turn.raw_text,
            evidence_note=(
                f"Contradictory evidence: playback state is {spoken} "
                f"but complete heard text is present: {heard_text!r}"
            ),
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
            requires_review=True,
        )

    if spoken == "heard":
        return DeliveryClassification(
            status="heard",
            is_agent=True,
            was_heard=True,
            was_cut=False,
            heard_text=turn.raw_text,
            raw_text=turn.raw_text,
            evidence_note="Line fully heard by customer according to playback metadata",
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
        )

    if spoken == "cut":
        return DeliveryClassification(
            status="cut",
            is_agent=True,
            was_heard=bool(heard_text and heard_text.strip()) if heard_text else None,
            was_cut=True,
            heard_text=heard_text,
            raw_text=turn.raw_text,
            evidence_note=f"Line was cut during playback; partial heard: '{heard_text}'",
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
            requires_review=not bool(heard_text and heard_text.strip()),
        )

    if spoken == "not_played":
        return DeliveryClassification(
            status="not_played",
            is_agent=True,
            was_heard=False,
            was_cut=False,
            heard_text=None,
            raw_text=turn.raw_text,
            evidence_note="Line was queued/intended but not played to the customer",
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
        )

    if spoken == "no_audio":
        return DeliveryClassification(
            status="no_audio",
            is_agent=True,
            was_heard=False,
            was_cut=False,
            heard_text=None,
            raw_text=turn.raw_text,
            evidence_note="Audio synthesis or playback produced no audio",
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
        )

    return DeliveryClassification(
        status="unknown",
        is_agent=True,
        was_heard=None,
        was_cut=False,
        heard_text=None,
        raw_text=turn.raw_text,
        evidence_note=(
            "Playback metadata absent on assistant line; delivery status unknown"
            if spoken is None
            else f"Unsupported playback state {spoken!r}; delivery status unknown"
        ),
        turn_id=turn.turn_id,
        turn_index=turn.turn_index,
    )


def reconcile_timeline(
    turns: list[TranscriptTurn],
    events: list[InteractionEvent] | None = None,
) -> TimelineReconciliation:
    classifications = [classify_delivery(turn) for turn in turns]
    agent_classifications = [
        classification for classification in classifications if classification.is_agent
    ]
    status_counts = dict(Counter(item.status for item in agent_classifications))
    mismatches = [
        {
            "turn_id": item.turn_id,
            "turn_index": item.turn_index,
            "status": item.status,
            "raw_text": item.raw_text,
            "heard_text": item.heard_text,
            "evidence": item.evidence_note,
        }
        for item in classifications
        if item.status == "mismatch"
    ]
    unknown_turn_indices = [
        item.turn_index
        for item in classifications
        if item.status == "unknown" and item.turn_index is not None
    ]
    timed_turn_count = sum(is_valid_turn_timing(turn) for turn in turns)
    timestamp_invalid_turn_count = sum(
        turn.start_s is not None
        and turn.end_s is not None
        and not is_valid_turn_timing(turn)
        for turn in turns
    )
    timestamp_missing_turn_count = (
        len(turns) - timed_turn_count - timestamp_invalid_turn_count
    )
    if timestamp_invalid_turn_count:
        timestamp_quality = "invalid"
    elif timed_turn_count == len(turns) and turns:
        timestamp_quality = "complete"
    elif timed_turn_count:
        timestamp_quality = "partial"
    else:
        timestamp_quality = "unknown"

    review_required = any(item.requires_review for item in classifications)
    if review_required:
        state: Literal["complete", "unknown", "review_required"] = "review_required"
    elif (
        not agent_classifications
        or any(item.status == "unknown" for item in agent_classifications)
        or unknown_turn_indices
        or timestamp_quality != "complete"
    ):
        state = "unknown"
    else:
        state = "complete"

    return TimelineReconciliation(
        state=state,
        review_required=review_required,
        playback_status_counts=status_counts,
        mismatches=mismatches,
        unknown_turn_indices=unknown_turn_indices,
        timestamp_quality=timestamp_quality,
        timed_turn_count=timed_turn_count,
        timestamp_missing_turn_count=timestamp_missing_turn_count,
        timestamp_invalid_turn_count=timestamp_invalid_turn_count,
        source_events=[
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "occurred_at": (
                    event.occurred_at.isoformat()
                    if event.occurred_at is not None
                    else None
                ),
                "payload": event.payload,
            }
            for event in events or []
        ],
    )

