from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.storage.orm import Base


def create_session_factory(url: str, **engine_kwargs):
    engine = create_engine(url, **engine_kwargs)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    factory.engine = engine
    return factory


def init_db(session_factory) -> None:
    engine = session_factory.engine
    Base.metadata.create_all(engine)

    additions = {
        "golden_dataset_labels": {
            "conversation_status": "VARCHAR(64)",
            "language_slice": "VARCHAR(64)",
        },
        "human_reviews": {"evaluation_id": "VARCHAR(128)"},
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN {column_name} {column_type}"
                        )
                    )
