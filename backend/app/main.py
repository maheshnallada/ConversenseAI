import os
from app.api.app import create_app
from app.storage.db import create_session_factory, init_db

# Read DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./conversense.sqlite3")

session_factory = create_session_factory(DATABASE_URL)
init_db(session_factory)

app = create_app(session_factory)


def get_app():
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

