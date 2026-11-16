from datetime import datetime, timezone

from sqlalchemy import select

from app.storage.orm import EvaluationBatchRow, EvaluationRunRow, HumanReviewRow
from app.storage.review_repo import HumanReviewRepository


def _insert_batch(session_factory, *, tenant_id, interaction_id, evaluation_id):
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            EvaluationRunRow(
                run_id=f"run-{evaluation_id}",
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                summary_json="{}",
                review_required=False,
                review_reasons_json="[]",
                started_at=now,
                completed_at=now,
            )
        )
        session.add(
            EvaluationBatchRow(
                evaluation_id=evaluation_id,
                run_id=f"run-{evaluation_id}",
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                batch_name="conversation_understanding",
                status="completed",
                model="test-model",
                prompt_version="1",
                schema_version="1",
                started_at=now,
                completed_at=now,
                input_tokens=None,
                output_tokens=None,
                raw_output=None,
                parsed_output_json="{}",
                validation_json="{}",
                review_required=False,
                review_status="NOT_REQUIRED",
                review_reasons_json="[]",
            )
        )


def test_review_targets_batch_evaluation_id_and_updates_batch(session_factory):
    interaction_id = "interaction-review"
    evaluation_id = "evaluation-batch-123"
    _insert_batch(
        session_factory,
        tenant_id="tenant_001",
        interaction_id=interaction_id,
        evaluation_id=evaluation_id,
    )
    review_repo = HumanReviewRepository(session_factory)

    review = review_repo.submit_review(
        tenant_id="tenant_001",
        interaction_id=interaction_id,
        evaluation_id=evaluation_id,
        reviewed_label="accepted",
        reviewer_name="QA Lead",
        review_decision="ACCEPTED",
        notes="Verified evidence.",
    )

    assert review["evaluation_id"] == evaluation_id
    assert review["review_decision"] == "ACCEPTED"
    with session_factory() as session:
        batch = session.scalar(
            select(EvaluationBatchRow).where(
                EvaluationBatchRow.evaluation_id == evaluation_id
            )
        )
    assert batch.review_status == "PASSED"
    assert batch.review_required is False


def test_historical_review_records_remain_readable(session_factory):
    with session_factory.begin() as session:
        session.add(
            HumanReviewRow(
                tenant_id="tenant_001",
                interaction_id="interaction-legacy",
                evaluator_id="legacy.outcome",
                original_label="old",
                reviewed_label="reviewed",
                review_decision="OVERRIDDEN",
                reviewer_name="Legacy reviewer",
                notes="Historical audit.",
                created_at=datetime.now(timezone.utc),
            )
        )

    reviews = HumanReviewRepository(session_factory).get_reviews_for_interaction(
        "tenant_001",
        "interaction-legacy",
    )

    assert len(reviews) == 1
    assert reviews[0]["evaluator_id"] == "legacy.outcome"
    assert reviews[0]["reviewed_label"] == "reviewed"
    assert reviews[0]["archived"] is True
