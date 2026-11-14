from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from app.domain.golden import GoldenCallLabel
from app.storage.orm import GoldenCallLabelRow


class GoldenDatasetRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def save_label(self, label: GoldenCallLabel) -> None:
        self.save_many([label])

    def save_many(self, labels: List[GoldenCallLabel]) -> None:
        if not labels:
            return

        now = datetime.now(timezone.utc)
        values = [
            {
                "call_id": label.call_id,
                "interaction_id": label.interaction_id,
                "what_happened": label.what_happened,
                "correct_outcome": label.correct_outcome,
                "facts_customer_gave": label.facts_customer_gave or "",
                "sentiment": label.sentiment,
                "emotion": label.emotion,
                "overall": label.overall,
                "first_thing_wrong_line": label.first_thing_wrong_line,
                "first_thing_wrong_what": label.first_thing_wrong_what,
                "never_rule_broken": label.never_rule_broken or "None",
                "reviewer_notes": label.reviewer_notes,
                "created_at": now,
            }
            for label in labels
        ]
        update_fields = {
            "interaction_id",
            "what_happened",
            "correct_outcome",
            "facts_customer_gave",
            "sentiment",
            "emotion",
            "overall",
            "first_thing_wrong_line",
            "first_thing_wrong_what",
            "never_rule_broken",
            "reviewer_notes",
        }

        with self.session_factory.begin() as session:
            dialect = session.get_bind().dialect.name
            if dialect == "sqlite":
                insert = sqlite_insert(GoldenCallLabelRow)
            elif dialect == "postgresql":
                insert = postgresql_insert(GoldenCallLabelRow)
            else:
                raise ValueError(f"Unsupported golden dataset database dialect: {dialect}")

            statement = insert.on_conflict_do_update(
                index_elements=[GoldenCallLabelRow.call_id],
                set_={field: getattr(insert.excluded, field) for field in update_fields},
            )
            session.execute(statement, values)

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

