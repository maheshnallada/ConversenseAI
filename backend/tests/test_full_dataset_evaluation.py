from pathlib import Path
import pytest
from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.transcript_repo import TranscriptRepository
from app.storage.orm import InteractionRow
from sqlalchemy import select

def test_full_dataset_evaluations_presence():
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / "backend" / "conversense.sqlite3"
    factory = create_session_factory(f"sqlite:///{db_path}")
    init_db(factory)

    eval_repo = EvaluationRepository(factory)

    with factory() as session:
        interactions = session.scalars(
            select(InteractionRow).where(InteractionRow.tenant_id == "health_campaign")
        ).all()

    assert len(interactions) == 50

    # Check each interaction has evaluations
    for inter in interactions:
        evals = eval_repo.get_by_interaction("health_campaign", inter.interaction_id)
        assert len(evals) >= 5, f"Interaction {inter.interaction_id} has only {len(evals)} evaluations"
        families = {e.family for e in evals}
        assert "compliance" in families
        assert "outcome" in families
        assert "experience" in families
        assert "quality" in families
        assert "facts" in families

