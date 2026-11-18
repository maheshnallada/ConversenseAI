from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


QUEUE_GENERAL = "stream:general"
QUEUE_EVALUATION = "stream:evaluation"
QUEUE_ANALYTICS = "stream:analytics"
QUEUE_DLQ = "stream:dlq"

DEFAULT_CONSUMER_GROUP = "conversense_workers"


@dataclass
class QueueMessage:
    tenant_id: str
    interaction_id: str
    stage: str
    payload: dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    retry_count: int = 0
    max_retries: int = 3
    correlation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "tenant_id": self.tenant_id,
            "interaction_id": self.interaction_id,
            "stage": self.stage,
            "payload": self.payload,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "correlation_id": self.correlation_id or "",
            "created_at": self.created_at,
            "error_reason": self.error_reason or "",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueMessage":
        return cls(
            message_id=str(data.get("message_id", str(uuid.uuid4()))),
            tenant_id=str(data.get("tenant_id", "")),
            interaction_id=str(data.get("interaction_id", "")),
            stage=str(data.get("stage", "general")),
            payload=data.get("payload", {}) if isinstance(data.get("payload"), dict) else {},
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            correlation_id=str(data.get("correlation_id") or None) if data.get("correlation_id") else None,
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            error_reason=str(data.get("error_reason") or None) if data.get("error_reason") else None,
        )
