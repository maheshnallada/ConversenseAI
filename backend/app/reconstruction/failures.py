from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.transcript import TranscriptTurn
from app.reconstruction.timing import calculate_overlap, is_valid_turn_timing


class FailureCategory(str, Enum):
    TECHNICAL = "technical"
    CONVERSATIONAL = "conversational"


@dataclass
class FailureRecord:
    failure_type: str
    category: FailureCategory
    turn_index: int | None
    time_s: float | None
    evidence: str


@dataclass
class FailureAnalysisResult:
    first_technical_failure: FailureRecord | None = None
    first_conversational_failure: FailureRecord | None = None
    all_failures: list[FailureRecord] = field(default_factory=list)
    technical_ordering_unknown: bool = False
    conversational_ordering_unknown: bool = False


def select_first_failure(
    failures: list[FailureRecord],
) -> tuple[FailureRecord | None, bool]:
    if not failures:
        return None, False
    if len(failures) == 1:
        return failures[0], False

    if all(failure.time_s is not None for failure in failures):
        return min(failures, key=lambda failure: failure.time_s), False

    if all(failure.turn_index is not None for failure in failures):
        return min(failures, key=lambda failure: failure.turn_index), False

    return None, True


def classify_unplayed_agent_turn(
    turns: list[TranscriptTurn],
    turn_index_in_list: int,
    call_meta: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    Determines whether an unplayed agent turn was an expected cancellation
    (due to customer disconnect or customer interruption/barge-in) or a
    genuine technical failure.

    Returns:
        tuple[reason_type, evidence_note]:
        - "cancelled_customer_interrupted": customer interrupted or spoke concurrently.
        - "cancelled_customer_disconnected": customer hung up / call ended around this turn.
        - "cancelled_machine_voicemail": voicemail / machine screener answered.
        - "technical_failure_unplayed": genuine technical failure where audio should have played.
    """
    meta = call_meta or {}
    t = turns[turn_index_in_list]
    t_start = t.start_s

    # 1. Direct barge-in flag on the turn
    if t.barged_in is True:
        return (
            "cancelled_customer_interrupted",
            "Agent playback cancelled because customer barged in",
        )

    # 2. Check surrounding customer turns for interruption / concurrent speech
    for j in (turn_index_in_list - 1, turn_index_in_list + 1):
        if 0 <= j < len(turns):
            other = turns[j]
            if other.speaker == "customer":
                o_start = other.start_s
                o_end = other.end_s
                if o_start is not None and t_start is not None:
                    # Overlap or customer spoke within [-1.5, +1.5]s of agent start
                    if abs(o_start - t_start) <= 1.5:
                        return (
                            "cancelled_customer_interrupted",
                            f"Customer spoke at {o_start:.2f}s during/near agent turn start ({t_start:.2f}s)",
                        )
                    # Customer was speaking when agent turn queued
                    if o_end is not None and (o_start <= t_start <= o_end + 0.5):
                        return (
                            "cancelled_customer_interrupted",
                            f"Customer was speaking [{o_start:.2f}s - {o_end:.2f}s] when agent turn queued",
                        )
                    # Preceding customer turn occurred right before agent turn (<2.5s)
                    if j == turn_index_in_list - 1 and 0 <= (t_start - o_start) <= 2.5:
                        return (
                            "cancelled_customer_interrupted",
                            f"Customer turn at {o_start:.2f}s preceded unplayed agent turn at {t_start:.2f}s",
                        )
                elif other.barged_in is True:
                    return (
                        "cancelled_customer_interrupted",
                        "Customer interruption flagged on adjacent turn",
                    )

    # 3. Check customer disconnect / call dropped
    line_usage = meta.get("usage", {}).get("line", {}) if isinstance(meta.get("usage"), dict) else {}
    call_timing = meta.get("call_timing", {}) if isinstance(meta.get("call_timing"), dict) else {}

    ended_at_s = (
        meta.get("ended_at_seconds")
        or call_timing.get("ended_at_seconds")
        or line_usage.get("connected_s")
        or meta.get("connected_s")
    )
    if ended_at_s is not None:
        try:
            ended_at_s = float(ended_at_s)
        except (ValueError, TypeError):
            ended_at_s = None

    end_reason = str(
        meta.get("end_reason")
        or call_timing.get("end_reason")
        or meta.get("disposition")
        or (meta.get("end_call") or {}).get("outcome")
        or ""
    ).lower()

    # Machine / voicemail
    if any(kw in end_reason for kw in ("voicemail", "machine", "screener")):
        return (
            "cancelled_machine_voicemail",
            "Call was answered or terminated by machine/voicemail",
        )

    is_dropped = any(
        kw in end_reason
        for kw in ("drop", "hung_up", "hangup", "disconnect", "left")
    )

    # If call ended at or close to turn start
    if ended_at_s is not None and t_start is not None:
        if t_start >= (ended_at_s - 2.0):
            return (
                "cancelled_customer_disconnected",
                f"Customer disconnected at {ended_at_s:.2f}s (turn start {t_start:.2f}s)",
            )

    # Check if any subsequent agent turns were actually heard
    subsequent_played = any(
        turns[k].speaker == "agent" and turns[k].playback_spoken == "heard"
        for k in range(turn_index_in_list + 1, len(turns))
    )

    if is_dropped and not subsequent_played:
        return (
            "cancelled_customer_disconnected",
            "Call disconnected/dropped before agent line could be played",
        )

    return (
        "technical_failure_unplayed",
        "Agent line was queued during active call but never played to customer",
    )


def detect_failures(
    turns: list[TranscriptTurn],
    call_meta: dict[str, Any] | None = None,
) -> FailureAnalysisResult:
    meta = call_meta or {}
    failures: list[FailureRecord] = []

    agent_wav_count = meta.get("agent_wav_count")

    if agent_wav_count == 0:
        failures.append(
            FailureRecord(
                failure_type="NO_AGENT_AUDIO",
                category=FailureCategory.TECHNICAL,
                turn_index=None,
                time_s=0.0,
                evidence="Call metadata reports zero agent audio recordings",
            )
        )

    # Turn-by-turn checks
    prev_agent_text: str | None = None

    for i, t in enumerate(turns):
        t_time = t.start_s if is_valid_turn_timing(t) else None

        if t.speaker == "agent":
            heard_text = t.playback_heard_text
            complete_cut_text = (
                t.playback_spoken == "cut"
                and bool(t.raw_text)
                and heard_text == t.raw_text
            )
            contradictory_no_play = (
                t.playback_spoken in {"not_played", "no_audio"}
                and bool(heard_text and heard_text.strip())
            )
            if complete_cut_text or contradictory_no_play:
                failures.append(
                    FailureRecord(
                        failure_type="PLAYBACK_METADATA_MISMATCH",
                        category=FailureCategory.TECHNICAL,
                        turn_index=t.turn_index,
                        time_s=t_time,
                        evidence=(
                            f"Playback state {t.playback_spoken!r} conflicts with "
                            f"heard text {heard_text!r}"
                        ),
                    )
                )
            elif t.playback_spoken == "cut":
                failures.append(
                    FailureRecord(
                        failure_type="AGENT_PLAYBACK_CUT",
                        category=FailureCategory.TECHNICAL,
                        turn_index=t.turn_index,
                        time_s=t_time,
                        evidence=f"Agent speech cut during playback; partial heard: '{heard_text or ''}'",
                    )
                )
            elif t.playback_spoken in {"not_played", "no_audio"}:
                reason, note = classify_unplayed_agent_turn(turns, i, meta)
                if reason == "technical_failure_unplayed":
                    failures.append(
                        FailureRecord(
                            failure_type="AGENT_LINE_NOT_PLAYED",
                            category=FailureCategory.TECHNICAL,
                            turn_index=t.turn_index,
                            time_s=t_time,
                            evidence=note,
                        )
                    )

            # Check agent repetition
            if prev_agent_text and len(t.normalized_text) > 8 and t.normalized_text == prev_agent_text:
                failures.append(
                    FailureRecord(
                        failure_type="AGENT_REPETITION",
                        category=FailureCategory.CONVERSATIONAL,
                        turn_index=t.turn_index,
                        time_s=t_time,
                        evidence=f"Agent repeated exact prompt: '{t.raw_text}'",
                    )
                )
            prev_agent_text = t.normalized_text

        if i > 0:
            prev = turns[i - 1]

            if t.speaker == "customer" and prev.speaker == "agent":
                overlap = calculate_overlap(prev.start_s, prev.end_s, t.start_s, t.end_s)
                if (overlap is not None and overlap > 0.0) or t.barged_in is True:
                    evidence = (
                        f"Customer spoke while agent was speaking (overlap: {overlap:.2f}s)"
                        if overlap is not None
                        else "Customer interruption explicitly marked; timing unavailable"
                    )
                    failures.append(
                        FailureRecord(
                            failure_type="CUSTOMER_INTERRUPTION",
                            category=FailureCategory.CONVERSATIONAL,
                            turn_index=t.turn_index,
                            time_s=t_time,
                            evidence=evidence,
                        )
                    )

            if t.speaker == "agent" and prev.speaker == "customer":
                if is_valid_turn_timing(prev) and is_valid_turn_timing(t):
                    latency = t.start_s - prev.end_s
                    if latency > 3.0:
                        failures.append(
                            FailureRecord(
                                failure_type="LONG_RESPONSE_DELAY",
                                category=FailureCategory.CONVERSATIONAL,
                                turn_index=t.turn_index,
                                time_s=t_time,
                                evidence=f"Agent delayed response by {latency:.2f}s after customer spoke (>3.0s)",
                            )
                        )

    if meta.get("end_reason") == "dropped" and turns:
        last_turn = turns[-1]
        last_time = last_turn.end_s if is_valid_turn_timing(last_turn) else None
        failures.append(
            FailureRecord(
                failure_type="CUSTOMER_DISCONNECT",
                category=FailureCategory.CONVERSATIONAL,
                turn_index=last_turn.turn_index,
                time_s=last_time,
                evidence="Customer disconnected/dropped call before reaching normal conclusion",
            )
        )

    tech_failures = [f for f in failures if f.category == FailureCategory.TECHNICAL]
    conv_failures = [f for f in failures if f.category == FailureCategory.CONVERSATIONAL]
    first_tech, technical_ordering_unknown = select_first_failure(tech_failures)
    first_conv, conversational_ordering_unknown = select_first_failure(conv_failures)

    return FailureAnalysisResult(
        first_technical_failure=first_tech,
        first_conversational_failure=first_conv,
        all_failures=failures,
        technical_ordering_unknown=technical_ordering_unknown,
        conversational_ordering_unknown=conversational_ordering_unknown,
    )

