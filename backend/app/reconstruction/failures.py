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
            elif t.playback_spoken == "not_played":
                failures.append(
                    FailureRecord(
                        failure_type="AGENT_LINE_NOT_PLAYED",
                        category=FailureCategory.TECHNICAL,
                        turn_index=t.turn_index,
                        time_s=t_time,
                        evidence="Agent line was queued but never played to customer",
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

