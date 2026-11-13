from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.domain.transcript import TranscriptTurn
from app.reconstruction.timing import calculate_overlap


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


def detect_failures(
    turns: list[TranscriptTurn],
    call_meta: dict[str, Any] | None = None,
) -> FailureAnalysisResult:
    meta = call_meta or {}
    failures: list[FailureRecord] = []

    agent_turns = [t for t in turns if t.speaker == "agent"]
    agent_wav_count = meta.get("agent_wav_count")

    # 1. NO_AGENT_AUDIO check
    if agent_wav_count == 0 or len(agent_turns) == 0:
        failures.append(
            FailureRecord(
                failure_type="NO_AGENT_AUDIO",
                category=FailureCategory.TECHNICAL,
                turn_index=None,
                time_s=0.0,
                evidence="Call has no agent audio or no agent messages recorded",
            )
        )

    # 2. LATE_AGENT_OPENING check
    if agent_turns:
        first_agent = agent_turns[0]
        if first_agent.start_s is not None and first_agent.start_s > 3.0:
            failures.append(
                FailureRecord(
                    failure_type="LATE_AGENT_OPENING",
                    category=FailureCategory.TECHNICAL,
                    turn_index=first_agent.turn_index,
                    time_s=first_agent.start_s,
                    evidence=f"First agent words came late at {first_agent.start_s:.2f}s (>3.0s threshold)",
                )
            )

    # 3. Turn-by-turn checks
    prev_agent_text: str | None = None

    for i, t in enumerate(turns):
        t_time = t.start_s if t.start_s is not None else 0.0

        # Technical failures on assistant delivery
        if t.speaker == "agent":
            if t.playback_spoken == "cut":
                failures.append(
                    FailureRecord(
                        failure_type="AGENT_PLAYBACK_CUT",
                        category=FailureCategory.TECHNICAL,
                        turn_index=t.turn_index,
                        time_s=t_time,
                        evidence=f"Agent speech cut during playback; partial heard: '{t.playback_heard_text or ''}'",
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

        # Check turn interactions with previous turn
        if i > 0:
            prev = turns[i - 1]

            # Interruption check: customer speaking over agent
            if t.speaker == "customer" and prev.speaker == "agent":
                overlap = calculate_overlap(prev.start_s, prev.end_s, t.start_s, t.end_s)
                if overlap > 0.0 or t.barged_in is True:
                    failures.append(
                        FailureRecord(
                            failure_type="CUSTOMER_INTERRUPTION",
                            category=FailureCategory.CONVERSATIONAL,
                            turn_index=t.turn_index,
                            time_s=t_time,
                            evidence=f"Customer spoke while agent was speaking (overlap: {overlap:.2f}s)",
                        )
                    )

            # Response delay check
            if t.speaker == "agent" and prev.speaker == "customer":
                if prev.end_s is not None and t.start_s is not None:
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

    # 4. Check for customer disconnect if call ended abruptly
    if meta.get("end_reason") == "dropped" and turns:
        last_turn = turns[-1]
        last_time = last_turn.end_s or last_turn.start_s or 0.0
        failures.append(
            FailureRecord(
                failure_type="CUSTOMER_DISCONNECT",
                category=FailureCategory.CONVERSATIONAL,
                turn_index=last_turn.turn_index,
                time_s=last_time,
                evidence="Customer disconnected/dropped call before reaching normal conclusion",
            )
        )

    # Separate earliest technical and conversational failures
    tech_failures = [f for f in failures if f.category == FailureCategory.TECHNICAL]
    conv_failures = [f for f in failures if f.category == FailureCategory.CONVERSATIONAL]

    first_tech = (
        min(tech_failures, key=lambda f: f.time_s if f.time_s is not None else 999999.0)
        if tech_failures
        else None
    )
    first_conv = (
        min(conv_failures, key=lambda f: f.time_s if f.time_s is not None else 999999.0)
        if conv_failures
        else None
    )

    return FailureAnalysisResult(
        first_technical_failure=first_tech,
        first_conversational_failure=first_conv,
        all_failures=failures,
    )

