from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class EvaluationBatchRecord:
    evaluation_id: str
    batch_name: str
    status: str
    model: str
    prompt_version: str
    schema_version: str
    started_at: datetime
    completed_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    raw_output: str | None
    parsed_output: dict[str, Any] | None
    validation: dict[str, Any]
    review_required: bool
    review_status: str
    review_reasons: list[str]
    source_evaluation_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class EvaluationRun:
    run_id: str
    tenant_id: str
    interaction_id: str
    batches: list[EvaluationBatchRecord]
    summary: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None
    review_required: bool
    review_reasons: list[str]

