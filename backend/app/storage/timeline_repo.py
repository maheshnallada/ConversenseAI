import json
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.domain.timeline import ReconstructedTimeline, TimelineEvent
from app.reconstruction.failures import FailureCategory, FailureRecord
from app.storage.orm import InteractionTimelineRow


class TimelineRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def save_timeline(self, timeline: ReconstructedTimeline) -> None:
        now = datetime.now(timezone.utc)
        timeline_dict = {
            "tenant_id": timeline.tenant_id,
            "interaction_id": timeline.interaction_id,
            "total_duration_s": timeline.total_duration_s,
            "agent_turn_count": timeline.agent_turn_count,
            "customer_turn_count": timeline.customer_turn_count,
            "overlap_count": timeline.overlap_count,
            "total_overlap_s": timeline.total_overlap_s,
            "events": [asdict(e) for e in timeline.events],
            "first_technical_failure": (
                asdict(timeline.first_technical_failure)
                if timeline.first_technical_failure
                else None
            ),
            "first_conversational_failure": (
                asdict(timeline.first_conversational_failure)
                if timeline.first_conversational_failure
                else None
            ),
        }

        first_tech = timeline.first_technical_failure
        first_conv = timeline.first_conversational_failure

        with self.session_factory() as session:
            session.execute(
                delete(InteractionTimelineRow).where(
                    InteractionTimelineRow.tenant_id == timeline.tenant_id,
                    InteractionTimelineRow.interaction_id == timeline.interaction_id,
                )
            )

            row = InteractionTimelineRow(
                tenant_id=timeline.tenant_id,
                interaction_id=timeline.interaction_id,
                total_duration_s=timeline.total_duration_s,
                agent_turn_count=timeline.agent_turn_count,
                customer_turn_count=timeline.customer_turn_count,
                overlap_count=timeline.overlap_count,
                total_overlap_s=timeline.total_overlap_s,
                first_technical_failure_type=first_tech.failure_type if first_tech else None,
                first_technical_failure_turn=first_tech.turn_index if first_tech else None,
                first_technical_failure_time_s=first_tech.time_s if first_tech else None,
                first_conversational_failure_type=first_conv.failure_type if first_conv else None,
                first_conversational_failure_turn=first_conv.turn_index if first_conv else None,
                first_conversational_failure_time_s=first_conv.time_s if first_conv else None,
                timeline_json=json.dumps(timeline_dict),
                created_at=now,
            )
            session.add(row)
            session.commit()

    def get_timeline(self, tenant_id: str, interaction_id: str) -> ReconstructedTimeline | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(InteractionTimelineRow).where(
                    InteractionTimelineRow.tenant_id == tenant_id,
                    InteractionTimelineRow.interaction_id == interaction_id,
                )
            )
            if row is None:
                return None

            data = json.loads(row.timeline_json)
            events = [TimelineEvent(**e) for e in data.get("events", [])]

            first_tech_data = data.get("first_technical_failure")
            first_tech = (
                FailureRecord(
                    failure_type=first_tech_data["failure_type"],
                    category=FailureCategory(first_tech_data["category"]),
                    turn_index=first_tech_data["turn_index"],
                    time_s=first_tech_data["time_s"],
                    evidence=first_tech_data["evidence"],
                )
                if first_tech_data
                else None
            )

            first_conv_data = data.get("first_conversational_failure")
            first_conv = (
                FailureRecord(
                    failure_type=first_conv_data["failure_type"],
                    category=FailureCategory(first_conv_data["category"]),
                    turn_index=first_conv_data["turn_index"],
                    time_s=first_conv_data["time_s"],
                    evidence=first_conv_data["evidence"],
                )
                if first_conv_data
                else None
            )

            return ReconstructedTimeline(
                tenant_id=data["tenant_id"],
                interaction_id=data["interaction_id"],
                total_duration_s=data["total_duration_s"],
                agent_turn_count=data["agent_turn_count"],
                customer_turn_count=data["customer_turn_count"],
                overlap_count=data["overlap_count"],
                total_overlap_s=data["total_overlap_s"],
                events=events,
                first_technical_failure=first_tech,
                first_conversational_failure=first_conv,
            )

