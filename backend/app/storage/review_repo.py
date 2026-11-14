from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.storage.orm import (
    EvaluationBatchRow,
    EvaluationRunRow,
    HumanReviewRow,
)


class HumanReviewRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def submit_review(
        self,
        tenant_id: str,
        interaction_id: str,
        evaluation_id: str,
        reviewed_label: str,
        reviewer_name: str,
        review_decision: str = "OVERRIDDEN",
        original_label: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if review_decision not in {"ACCEPTED", "OVERRIDDEN"}:
            raise ValueError(f"Unsupported review decision: {review_decision!r}.")
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            batch = session.scalar(
                select(EvaluationBatchRow).where(
                    EvaluationBatchRow.tenant_id == tenant_id,
                    EvaluationBatchRow.interaction_id == interaction_id,
                    EvaluationBatchRow.evaluation_id == evaluation_id,
                )
            )
            if batch is None:
                raise ValueError(
                    f"Evaluation {evaluation_id!r} was not found for "
                    f"{tenant_id}:{interaction_id}."
                )
            batch.review_status = (
                "PASSED" if review_decision == "ACCEPTED" else "OVERRIDDEN"
            )
            batch.review_required = False
            batch.review_reasons_json = "[]"

            run = session.scalar(
                select(EvaluationRunRow).where(
                    EvaluationRunRow.tenant_id == tenant_id,
                    EvaluationRunRow.interaction_id == interaction_id,
                    EvaluationRunRow.run_id == batch.run_id,
                )
            )
            if run is not None:
                other_batches = session.scalars(
                    select(EvaluationBatchRow).where(
                        EvaluationBatchRow.tenant_id == tenant_id,
                        EvaluationBatchRow.interaction_id == interaction_id,
                        EvaluationBatchRow.run_id == batch.run_id,
                    )
                ).all()
                run.review_required = any(
                    item.review_required for item in other_batches
                )

            review_row = HumanReviewRow(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                evaluator_id=evaluation_id,
                evaluation_id=evaluation_id,
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
                "evaluation_id": evaluation_id,
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
                    "evaluation_id": r.evaluation_id,
                    "original_label": r.original_label,
                    "reviewed_label": r.reviewed_label,
                    "review_decision": r.review_decision,
                    "reviewer_name": r.reviewer_name,
                    "notes": r.notes,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "archived": r.evaluation_id is None,
                }
                for r in rows
            ]

