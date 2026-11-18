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
        raw_meta = call_metadata or {}
        meta = dict(raw_meta)
        if "meta" in meta and isinstance(meta["meta"], dict):
            # Flatten so nested usage / line info and top-level end_reason are both accessible
            meta = {**meta["meta"], **meta}
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

            # Analyze timing against previous turn before adding current turn
            if i > 0:
                prev = turns[i - 1]
                timing_analysis = analyze_turn_pair(prev, t)

                # Detect noticeable silence gap (> 2.0s) occurring before current turn
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
                    "line": t.turn_index + 1,
                    "turn_index": t.turn_index,
                    "normalized_text": t.normalized_text,
                    "playback_spoken": t.playback_spoken,
                    "playback_heard_text": t.playback_heard_text,
                    "barged_in": t.barged_in,
                    "delivery_evidence": delivery.evidence_note,
                },
            )
            timeline_events.append(turn_event)

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

        # Detect booking / callback event to place on reconstructed timeline
        booking_src = None
        callback_src = None
        if events:
            for ev in events:
                etype = (
                    getattr(ev, "event_type", None)
                    or (ev.get("event_type") if isinstance(ev, dict) else None)
                )
                if etype in {"appointment.booked", "booking.confirmed"}:
                    booking_src = ev
                elif etype in {"callback.scheduled", "callback"}:
                    callback_src = ev

        end_call = meta.get("end_call")
        if not end_call and isinstance(meta.get("meta"), dict):
            end_call = meta["meta"].get("end_call")

        rec = (
            end_call.get("record")
            if isinstance(end_call, dict) and isinstance(end_call.get("record"), dict)
            else {}
        )
        outcome = (
            str(end_call.get("outcome") or "").strip().upper()
            if isinstance(end_call, dict)
            else ""
        )

        booking_payload = (
            getattr(booking_src, "payload", {})
            if booking_src
            else (booking_src.get("payload", {}) if isinstance(booking_src, dict) else {})
        )
        callback_payload = (
            getattr(callback_src, "payload", {})
            if callback_src
            else (callback_src.get("payload", {}) if isinstance(callback_src, dict) else {})
        )

        expert_call_at = (
            booking_payload.get("appointment_at")
            or rec.get("expert_call_at")
            or (end_call.get("expert_call_at") if isinstance(end_call, dict) else None)
        )
        call_later_at = (
            callback_payload.get("callback_at")
            or rec.get("call_later_at")
            or (end_call.get("call_later_at") if isinstance(end_call, dict) else None)
        )

        booking_time = total_duration if total_duration is not None else (
            max_end_s if max_end_s is not None else (
                turns[-1].end_s if turns and turns[-1].end_s is not None else 0.0
            )
        )
        if booking_time is not None:
            booking_time = round(booking_time, 2)

        if booking_src or outcome in {"CALLBACK_BOOKED", "APPOINTMENT_BOOKED"} or expert_call_at:
            booking_meta = {
                "event_type": "appointment.booked",
                "outcome": outcome or booking_payload.get("outcome", "CALLBACK_BOOKED"),
                "appointment_at": expert_call_at,
                "commitments": (
                    booking_payload.get("commitments")
                    or (end_call.get("commitments", []) if isinstance(end_call, dict) else [])
                ),
                "summary": (
                    booking_payload.get("summary")
                    or (end_call.get("summary") if isinstance(end_call, dict) else None)
                ),
                "closing_line": (
                    booking_payload.get("closing_line")
                    or (end_call.get("closing_line") if isinstance(end_call, dict) else None)
                ),
            }
            timeline_events.append(
                TimelineEvent(
                    event_id=f"booking_{interaction_id}",
                    event_type="booking",
                    speaker="agent",
                    start_s=booking_time,
                    end_s=booking_time,
                    duration_s=0.0,
                    text=f"Appointment Booked: {expert_call_at}" if expert_call_at else "Appointment Booked",
                    metadata=booking_meta,
                )
            )
        elif callback_src or outcome == "CALL_LATER" or call_later_at:
            callback_meta = {
                "event_type": "callback.scheduled",
                "outcome": outcome or callback_payload.get("outcome", "CALL_LATER"),
                "callback_at": call_later_at,
                "commitments": (
                    callback_payload.get("commitments")
                    or (end_call.get("commitments", []) if isinstance(end_call, dict) else [])
                ),
                "summary": (
                    callback_payload.get("summary")
                    or (end_call.get("summary") if isinstance(end_call, dict) else None)
                ),
                "closing_line": (
                    callback_payload.get("closing_line")
                    or (end_call.get("closing_line") if isinstance(end_call, dict) else None)
                ),
            }
            timeline_events.append(
                TimelineEvent(
                    event_id=f"callback_{interaction_id}",
                    event_type="callback",
                    speaker="agent",
                    start_s=booking_time,
                    end_s=booking_time,
                    duration_s=0.0,
                    text=f"Callback Scheduled: {call_later_at}" if call_later_at else "Callback Scheduled",
                    metadata=callback_meta,
                )
            )

        # Sort timeline events chronologically for proper visual and logical alignment
        timeline_events.sort(
            key=lambda ev: (
                ev.start_s if ev.start_s is not None else float("inf"),
                0 if ev.event_type == "turn" else 1,
            )
        )

        # Detect failures
        failure_res = detect_failures(turns, meta)

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

