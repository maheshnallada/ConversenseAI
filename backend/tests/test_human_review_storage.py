import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.storage.db import create_session_factory, init_db
from app.storage.orm import EvaluationResultRow
from app.storage.review_repo import HumanReviewRepository

@pytest.fixture
def review_repo():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)
    return HumanReviewRepository(factory)

def test_submit_and_get_human_review(review_repo):
    unique_call_id = f"call_rev_{uuid.uuid4().hex[:8]}"

    review = review_repo.submit_review(
        tenant_id="health_campaign",
        interaction_id=unique_call_id,
        evaluator_id="outcome.intent",
        original_label="Can't tell",
        reviewed_label="Not interested",
        review_decision="OVERRIDDEN",
        reviewer_name="QA Lead",
        notes="Customer clearly declined on line 5.",
    )

    assert review["interaction_id"] == unique_call_id
    assert review["review_decision"] == "OVERRIDDEN"

    reviews = review_repo.get_reviews_for_interaction("health_campaign", unique_call_id)
    assert len(reviews) == 1
    assert reviews[0]["reviewer_name"] == "QA Lead"
    assert reviews[0]["reviewed_label"] == "Not interested"


def test_review_updates_latest_evaluator_version(review_repo):
    interaction_id = f"call_rev_versions_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    with review_repo.session_factory() as session:
        for version, label, created_at in (
            ("1.0.0", "Older result", now - timedelta(days=1)),
            ("2.0.0", "Latest result", now),
        ):
            session.add(
                EvaluationResultRow(
                    tenant_id="health_campaign",
                    interaction_id=interaction_id,
                    evaluator_id="outcome.intent",
                    evaluator_version=version,
                    family="outcome",
                    method="deterministic",
                    label=label,
                    score=0.5,
                    confidence=0.8,
                    severity="low",
                    review_status="PASSED",
                    evidence_json="[]",
                    reason="test result",
                    details_json="{}",
                    created_at=created_at,
                )
            )
        session.commit()

    review = review_repo.submit_review(
        tenant_id="health_campaign",
        interaction_id=interaction_id,
        evaluator_id="outcome.intent",
        reviewed_label="Accepted latest",
        reviewer_name="Reviewer",
    )

    assert review["original_label"] == "Latest result"
    with review_repo.session_factory() as session:
        rows = session.scalars(
            select(EvaluationResultRow).where(
                EvaluationResultRow.tenant_id == "health_campaign",
                EvaluationResultRow.interaction_id == interaction_id,
            )
        ).all()

    labels_by_version = {row.evaluator_version: row.label for row in rows}
    assert labels_by_version == {
        "1.0.0": "Older result",
        "2.0.0": "Accepted latest",
    }
