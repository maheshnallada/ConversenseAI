from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.storage.orm import Base


def create_session_factory(url: str, **engine_kwargs):
    engine = create_engine(url, **engine_kwargs)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    factory.engine = engine
    return factory


def init_db(session_factory) -> None:
    Base.metadata.create_all(session_factory.engine)
