from typing import Any

from app.domain.timeline import ReconstructedTimeline, TimelineEvent
from app.domain.transcript import TranscriptTurn
from app.reconstruction.failures import detect_failures
from app.reconstruction.reconciliation import classify_delivery
from app.reconstruction.timing import analyze_turn_pair


class TimelineReconstructor:
    def reconstruct(
        self,
        tenant_id: str,
        interaction_id: str,
        turns: list[TranscriptTurn],
        call_metadata: dict[str, Any] | None = None,
    ) -> ReconstructedTimeline:
        meta = call_metadata or {}
        events: list[TimelineEvent] = []

        agent_turn_count = 0
        customer_turn_count = 0
        overlap_count = 0
        total_overlap_s = 0.0

        max_end_s = 0.0

        for i, t in enumerate(turns):
            if t.speaker == "agent":
                agent_turn_count += 1
            elif t.speaker == "customer":
                customer_turn_count += 1

            delivery = classify_delivery(t)

            if t.end_s is not None and t.end_s > max_end_s:
                max_end_s = t.end_s
            elif t.start_s is not None and t.start_s > max_end_s:
                max_end_s = t.start_s

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
            events.append(turn_event)

            # Analyze timing against previous turn
            if i > 0:
                prev = turns[i - 1]
                timing_analysis = analyze_turn_pair(prev, t)

                if timing_analysis.is_interruption and timing_analysis.overlap_s > 0.0:
                    overlap_count += 1
                    total_overlap_s += timing_analysis.overlap_s
                    events.append(
                        TimelineEvent(
                            event_id=f"overlap_{prev.turn_index}_{t.turn_index}",
                            event_type="interruption",
                            speaker=timing_analysis.interrupter,
                            start_s=t.start_s,
                            end_s=min(prev.end_s, t.end_s) if (prev.end_s and t.end_s) else t.start_s,
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
                    events.append(
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

        total_duration = meta.get("connected_s") or max_end_s or 0.0

        return ReconstructedTimeline(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            total_duration_s=round(float(total_duration), 2),
            agent_turn_count=agent_turn_count,
            customer_turn_count=customer_turn_count,
            overlap_count=overlap_count,
            total_overlap_s=round(total_overlap_s, 2),
            events=events,
            first_technical_failure=failure_res.first_technical_failure,
            first_conversational_failure=failure_res.first_conversational_failure,
        )

