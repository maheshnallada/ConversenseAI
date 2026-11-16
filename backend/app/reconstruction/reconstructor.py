from typing import Any

from app.domain.envelope import InteractionEvent
from app.domain.timeline import ReconstructedTimeline, TimelineEvent
from app.domain.transcript import TranscriptTurn
from app.reconstruction.failures import detect_failures
from app.reconstruction.reconciliation import classify_delivery, reconcile_timeline
from app.reconstruction.timing import analyze_turn_pair, is_valid_turn_timing


class TimelineReconstructor:
    def reconstruct(
        self,
        tenant_id: str,
        interaction_id: str,
        turns: list[TranscriptTurn],
        call_metadata: dict[str, Any] | None = None,
        events: list[InteractionEvent] | None = None,
    ) -> ReconstructedTimeline:
        meta = call_metadata or {}
        timeline_events: list[TimelineEvent] = []

        agent_turn_count = 0
        customer_turn_count = 0
        overlap_count = 0
        total_overlap_s = 0.0

        max_end_s: float | None = None

        for i, t in enumerate(turns):
            if t.speaker == "agent":
                agent_turn_count += 1
            elif t.speaker == "customer":
                customer_turn_count += 1

            delivery = classify_delivery(t)

            if is_valid_turn_timing(t) and t.end_s is not None:
                max_end_s = t.end_s if max_end_s is None else max(max_end_s, t.end_s)

            # Add primary turn event
            turn_event = TimelineEvent(
                event_id=f"turn_{t.turn_index}",
                event_type="turn",
                speaker=t.speaker,
                start_s=t.start_s,
                end_s=t.end_s,
                duration_s=t.duration_s,
                text=t.raw_text,
                delivery_status=delivery.status,
                metadata={
                    "normalized_text": t.normalized_text,
                    "playback_spoken": t.playback_spoken,
                    "playback_heard_text": t.playback_heard_text,
                    "barged_in": t.barged_in,
                    "delivery_evidence": delivery.evidence_note,
                },
            )
            timeline_events.append(turn_event)

            # Analyze timing against previous turn
            if i > 0:
                prev = turns[i - 1]
                timing_analysis = analyze_turn_pair(prev, t)

                if (
                    timing_analysis.is_interruption
                    and timing_analysis.overlap_s is not None
                    and timing_analysis.overlap_s > 0.0
                ):
                    overlap_count += 1
                    total_overlap_s += timing_analysis.overlap_s
                    timeline_events.append(
                        TimelineEvent(
                            event_id=f"overlap_{prev.turn_index}_{t.turn_index}",
                            event_type="interruption",
                            speaker=timing_analysis.interrupter,
                            start_s=t.start_s,
                            end_s=(
                                min(prev.end_s, t.end_s)
                                if prev.end_s is not None and t.end_s is not None
                                else t.start_s
                            ),
                            duration_s=timing_analysis.overlap_s,
                            text=None,
                            delivery_status=None,
                            metadata={
                                "interrupter": timing_analysis.interrupter,
                                "prev_turn_index": prev.turn_index,
                                "next_turn_index": t.turn_index,
                            },
                        )
                    )

                # Detect noticeable silence gap (> 2.0s)
                if (
                    timing_analysis.silence_gap_s is not None
                    and timing_analysis.silence_gap_s > 2.0
                ):
                    timeline_events.append(
                        TimelineEvent(
                            event_id=f"silence_{prev.turn_index}_{t.turn_index}",
                            event_type="silence",
                            start_s=prev.end_s,
                            end_s=t.start_s,
                            duration_s=timing_analysis.silence_gap_s,
                            metadata={
                                "prev_turn_index": prev.turn_index,
                                "next_turn_index": t.turn_index,
                            },
                        )
                    )

        # Detect failures
        failure_res = detect_failures(turns, meta)

        connected_s = meta.get("connected_s")
        if (
            isinstance(connected_s, (int, float))
            and not isinstance(connected_s, bool)
            and 0.0 <= connected_s < float("inf")
        ):
            total_duration = round(float(connected_s), 2)
        elif turns and all(is_valid_turn_timing(turn) for turn in turns):
            total_duration = round(max_end_s, 2) if max_end_s is not None else None
        else:
            total_duration = None

        return ReconstructedTimeline(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            total_duration_s=total_duration,
            agent_turn_count=agent_turn_count,
            customer_turn_count=customer_turn_count,
            overlap_count=overlap_count,
            total_overlap_s=round(total_overlap_s, 2),
            events=timeline_events,
            first_technical_failure=failure_res.first_technical_failure,
            first_conversational_failure=failure_res.first_conversational_failure,
            reconciliation=reconcile_timeline(turns, events=events),
            technical_failure_ordering_unknown=failure_res.technical_ordering_unknown,
            conversational_failure_ordering_unknown=failure_res.conversational_ordering_unknown,
            failures=failure_res.all_failures,
        )

