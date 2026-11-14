import uuid
from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
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
