import os
from app.api.app import create_app
from app.storage.db import create_session_factory, init_db

# Read DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./conversense.sqlite3")

session_factory = create_session_factory(DATABASE_URL)
init_db(session_factory)

# Auto-seed golden dataset labels if empty
try:
    from pathlib import Path
    from app.storage.golden_repo import GoldenDatasetRepository
    from app.validation.golden_loader import load_golden_dataset

    golden_repo = GoldenDatasetRepository(session_factory)
    if not golden_repo.get_all():
        for cand in [Path("data/golden_dataset.csv"), Path(__file__).resolve().parent.parent.parent / "data" / "golden_dataset.csv"]:
            if cand.exists():
                labels = load_golden_dataset(cand)
                golden_repo.save_many(labels)
                break
except Exception:
    pass

app = create_app(session_factory)


def get_app():
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

