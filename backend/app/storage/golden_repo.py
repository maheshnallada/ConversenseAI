from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker

from app.domain.golden import GoldenCallLabel
from app.storage.orm import GoldenCallLabelRow


class GoldenDatasetRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def save_label(self, label: GoldenCallLabel) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            existing = session.scalar(
                select(GoldenCallLabelRow).where(GoldenCallLabelRow.call_id == label.call_id)
            )
            if existing:
                existing.interaction_id = label.interaction_id
                existing.what_happened = label.what_happened
                existing.correct_outcome = label.correct_outcome
                existing.facts_customer_gave = label.facts_customer_gave or ""
                existing.sentiment = label.sentiment
                existing.emotion = label.emotion
                existing.overall = label.overall
                existing.first_thing_wrong_line = label.first_thing_wrong_line
                existing.first_thing_wrong_what = label.first_thing_wrong_what
                existing.never_rule_broken = label.never_rule_broken or "None"
                existing.reviewer_notes = label.reviewer_notes
            else:
                row = GoldenCallLabelRow(
                    call_id=label.call_id,
                    interaction_id=label.interaction_id,
                    what_happened=label.what_happened,
                    correct_outcome=label.correct_outcome,
                    facts_customer_gave=label.facts_customer_gave or "",
                    sentiment=label.sentiment,
                    emotion=label.emotion,
                    overall=label.overall,
                    first_thing_wrong_line=label.first_thing_wrong_line,
                    first_thing_wrong_what=label.first_thing_wrong_what,
                    never_rule_broken=label.never_rule_broken or "None",
                    reviewer_notes=label.reviewer_notes,
                    created_at=now,
                )
                session.add(row)
            session.commit()

    def save_many(self, labels: List[GoldenCallLabel]) -> None:
        for lbl in labels:
            self.save_label(lbl)

    def get_by_call_id(self, call_id: str) -> Optional[GoldenCallLabel]:
        with self.session_factory() as session:
            row = session.scalar(
                select(GoldenCallLabelRow).where(GoldenCallLabelRow.call_id == call_id)
            )
            if not row:
                return None
            return self._to_domain(row)

    def get_all(self) -> List[GoldenCallLabel]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(GoldenCallLabelRow).order_by(GoldenCallLabelRow.call_id.asc())
            ).all()
            return [self._to_domain(r) for r in rows]

    def _to_domain(self, row: GoldenCallLabelRow) -> GoldenCallLabel:
        return GoldenCallLabel(
            call_id=row.call_id,
            interaction_id=row.interaction_id,
            what_happened=row.what_happened,
            correct_outcome=row.correct_outcome,
            facts_customer_gave=row.facts_customer_gave,
            sentiment=row.sentiment,
            emotion=row.emotion,
            overall=row.overall,
            first_thing_wrong_line=row.first_thing_wrong_line,
            first_thing_wrong_what=row.first_thing_wrong_what,
            never_rule_broken=row.never_rule_broken,
            reviewer_notes=row.reviewer_notes,
        )

