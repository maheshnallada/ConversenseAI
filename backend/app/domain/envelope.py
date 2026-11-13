from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"
InteractionStatus = Literal["completed", "failed", "abandoned", "unknown", "pending"]


class Execution(BaseModel):
    """Model execution facts. None means unknown; zero means measured zero."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    cost: float | None = None
    currency: str | None = None


class InteractionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    occurred_at: datetime | None = None
    payload: dict[str, Any] | None = None


class ArtifactReference(BaseModel):
    """Reference to a stored artifact. Audio is a review artifact, not a transcript source."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    uri: str | None = None
    media_type: str | None = None
    sha256: str | None = None


class InteractionEnvelope(BaseModel):
    """Versioned canonical interaction. Omitted fields stay null rather than becoming zero."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    interaction_id: str = Field(min_length=1)
    session_id: str | None = None
    use_case: str | None = None
    interaction_type: str | None = None
    schema_version: Literal["1.0"]
    status: InteractionStatus | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    participants: list[dict[str, Any]] | None = None
    events: list[InteractionEvent] | None = None
    artifacts: list[ArtifactReference] | None = None
    execution: Execution | None = None
    observability: dict[str, Any] | None = None
    domain_data: dict[str, Any] | None = None
    evaluation_refs: list[Any] | None = None
