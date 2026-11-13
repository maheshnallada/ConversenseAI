import pytest

from app.ingestion.errors import IdempotencyConflict
from tests.conftest import sample_envelope


def test_ingest_then_retrieve_by_tenant(service, envelope):
    result = service.ingest(envelope)

    assert result.created is True
    stored = service.get(envelope.tenant_id, envelope.interaction_id)

    assert stored is not None
    assert stored.tenant_id == envelope.tenant_id
    assert stored.interaction_id == envelope.interaction_id
    assert stored.execution.input_tokens == 0
    assert stored.execution.output_tokens == 12
    assert stored.execution.cost is None


def test_retry_of_same_payload_returns_original_and_one_outbox_row(service, envelope):
    first = service.ingest(envelope)
    second = service.ingest(envelope)

    assert first.created is True
    assert second.created is False
    assert second.interaction.interaction_id == first.interaction.interaction_id
    assert service.outbox_count(envelope.tenant_id, envelope.interaction_id) == 1
    assert service.unpublished_outbox_count(envelope.tenant_id, envelope.interaction_id) == 1


def test_same_identity_with_different_payload_conflicts(service, envelope):
    service.ingest(envelope)
    changed = sample_envelope(use_case="customer_support")

    with pytest.raises(IdempotencyConflict):
        service.ingest(changed)

    assert service.outbox_count(envelope.tenant_id, envelope.interaction_id) == 1
    assert service.get(envelope.tenant_id, envelope.interaction_id).use_case == "health_insurance"


def test_other_tenant_cannot_retrieve_interaction(service, envelope):
    service.ingest(envelope)

    assert service.get("tenant_999", envelope.interaction_id) is None


def test_same_interaction_id_is_allowed_for_another_tenant(service, envelope):
    service.ingest(envelope)
    other = sample_envelope(tenant_id="tenant_002", use_case="customer_support")

    result = service.ingest(other)

    assert result.created is True
    assert service.get("tenant_002", envelope.interaction_id).use_case == "customer_support"
    assert service.get("tenant_001", envelope.interaction_id).use_case == "health_insurance"
