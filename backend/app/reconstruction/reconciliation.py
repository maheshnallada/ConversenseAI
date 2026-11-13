from dataclasses import dataclass
from typing import Literal

from app.domain.transcript import TranscriptTurn

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


def classify_delivery(turn: TranscriptTurn) -> DeliveryClassification:
    if turn.speaker != "agent":
        return DeliveryClassification(
            status="customer_turn" if turn.speaker == "customer" else "system_turn",
            is_agent=False,
            was_heard=True,
            was_cut=False,
            heard_text=None,
            raw_text=turn.raw_text,
            evidence_note="Customer or non-agent turn",
        )

    spoken = turn.playback_spoken
    heard_text = turn.playback_heard_text

    # Check for contradictory evidence
    if spoken == "not_played" and heard_text and heard_text.strip():
        return DeliveryClassification(
            status="mismatch",
            is_agent=True,
            was_heard=None,
            was_cut=False,
            heard_text=heard_text,
            raw_text=turn.raw_text,
            evidence_note=f"Contradictory evidence: metadata.spoken is not_played but heard text is present: '{heard_text}'",
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
        )

    if spoken == "cut":
        return DeliveryClassification(
            status="cut",
            is_agent=True,
            was_heard=True,
            was_cut=True,
            heard_text=heard_text,
            raw_text=turn.raw_text,
            evidence_note=f"Line was cut during playback; partial heard: '{heard_text}'",
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
        )

    # Missing metadata.spoken (e.g. all 12 studio calls)
    return DeliveryClassification(
        status="unknown",
        is_agent=True,
        was_heard=None,
        was_cut=False,
        heard_text=None,
        raw_text=turn.raw_text,
        evidence_note="Playback metadata absent on assistant line; delivery status unknown",
    )

