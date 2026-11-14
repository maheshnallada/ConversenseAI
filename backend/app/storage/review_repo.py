from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker

from app.storage.orm import HumanReviewRow, EvaluationResultRow


class HumanReviewRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def submit_review(
        self,
        tenant_id: str,
        interaction_id: str,
        evaluator_id: str,
        reviewed_label: str,
        reviewer_name: str,
        review_decision: str = "OVERRIDDEN",
        original_label: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            # 1. Update the evaluation_results row if it exists
            eval_row = session.scalar(
                select(EvaluationResultRow).where(
                    EvaluationResultRow.tenant_id == tenant_id,
                    EvaluationResultRow.interaction_id == interaction_id,
                    EvaluationResultRow.evaluator_id == evaluator_id,
                ).order_by(
                    desc(EvaluationResultRow.created_at),
                    desc(EvaluationResultRow.id),
                ).limit(1)
            )
            if eval_row:
                if not original_label:
                    original_label = eval_row.label
                eval_row.label = reviewed_label
                eval_row.review_status = "PASSED" if review_decision == "ACCEPTED" else "OVERRIDDEN"

            # 2. Add an audit entry to human_reviews
            review_row = HumanReviewRow(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                evaluator_id=evaluator_id,
                original_label=original_label,
                reviewed_label=reviewed_label,
                review_decision=review_decision,
                reviewer_name=reviewer_name,
                notes=notes,
                created_at=now,
            )
            session.add(review_row)
            session.commit()

            return {
                "id": review_row.id,
                "tenant_id": tenant_id,
                "interaction_id": interaction_id,
                "evaluator_id": evaluator_id,
                "original_label": original_label,
                "reviewed_label": reviewed_label,
                "review_decision": review_decision,
                "reviewer_name": reviewer_name,
                "notes": notes,
                "created_at": now.isoformat(),
            }

    def get_reviews_for_interaction(
        self,
        tenant_id: str,
        interaction_id: str,
    ) -> List[Dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(HumanReviewRow)
                .where(
                    HumanReviewRow.tenant_id == tenant_id,
                    HumanReviewRow.interaction_id == interaction_id,
                )
                .order_by(HumanReviewRow.created_at.desc())
            ).all()

            return [
                {
                    "id": r.id,
                    "tenant_id": r.tenant_id,
                    "interaction_id": r.interaction_id,
                    "evaluator_id": r.evaluator_id,
                    "original_label": r.original_label,
                    "reviewed_label": r.reviewed_label,
                    "review_decision": r.review_decision,
                    "reviewer_name": r.reviewer_name,
                    "notes": r.notes,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

