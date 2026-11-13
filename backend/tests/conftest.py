import pytest
from sqlalchemy.pool import StaticPool

from app.domain.envelope import Execution, InteractionEnvelope
from app.ingestion.service import IngestionService
from app.storage.db import create_session_factory, init_db


@pytest.fixture
def session_factory():
    factory = create_session_factory(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(factory)
    return factory


@pytest.fixture
def service(session_factory):
    return IngestionService(session_factory)


def sample_envelope(**overrides) -> InteractionEnvelope:
    data = {
        "tenant_id": "tenant_001",
        "interaction_id": "interaction_001",
        "schema_version": "1.0",
        "use_case": "health_insurance",
        "interaction_type": "voice",
    }
    data.update(overrides)
    return InteractionEnvelope(**data)


@pytest.fixture
def envelope():
    return sample_envelope(
        execution=Execution(input_tokens=0, output_tokens=12, cost=None)
    )
