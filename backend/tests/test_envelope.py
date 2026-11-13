import pytest
from pydantic import ValidationError

from app.domain.envelope import Execution, InteractionEnvelope


def test_schema_version_must_be_supported():
    with pytest.raises(ValidationError):
        InteractionEnvelope(
            tenant_id="tenant_001",
            interaction_id="interaction_001",
            schema_version="9.9",
        )


def test_omitted_execution_stays_unknown():
    envelope = InteractionEnvelope(
        tenant_id="tenant_001",
        interaction_id="interaction_001",
        schema_version="1.0",
    )
    assert envelope.execution is None
    assert envelope.status is None
    assert envelope.events is None
    assert envelope.artifacts is None


def test_explicit_zero_tokens_are_preserved():
    envelope = InteractionEnvelope(
        tenant_id="tenant_001",
        interaction_id="interaction_001",
        schema_version="1.0",
        execution=Execution(input_tokens=0, output_tokens=0, cost=0),
    )
    assert envelope.execution.input_tokens == 0
    assert envelope.execution.output_tokens == 0
    assert envelope.execution.cost == 0


def test_empty_event_list_is_not_rewritten_to_unknown():
    envelope = InteractionEnvelope(
        tenant_id="tenant_001",
        interaction_id="interaction_001",
        schema_version="1.0",
        events=[],
    )
    assert envelope.events == []


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        InteractionEnvelope(
            tenant_id="tenant_001",
            interaction_id="interaction_001",
            schema_version="1.0",
            invented_outcome="CALLBACK_BOOKED",
        )


def test_domain_data_can_carry_use_case_fields_without_a_core_enum():
    envelope = InteractionEnvelope(
        tenant_id="tenant_001",
        interaction_id="interaction_001",
        schema_version="1.0",
        use_case="customer_support",
        domain_data={"issue_resolved": None, "category": "billing"},
    )
    assert envelope.use_case == "customer_support"
    assert envelope.domain_data["issue_resolved"] is None
