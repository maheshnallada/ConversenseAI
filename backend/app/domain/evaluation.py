from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

EvaluationFamily = Literal[
    "technical",
    "outcome",
    "compliance",
    "experience",
    "quality",
    "facts",
]

EvaluationMethod = Literal[
    "deterministic",
    "llm",
    "hybrid",
    "human",
]

ReviewStatus = Literal[
    "PASSED",
    "FLAGGED_FOR_REVIEW",
    "FAILED",
]


@dataclass
class EvidenceItem:
    source_type: str
    reference_id: str
    line_index: int | None = None
    text_snippet: str | None = None
    timestamp_s: float | None = None
    reason: str = ""


@dataclass
class EvaluationResult:
    tenant_id: str
    interaction_id: str
    evaluator_id: str
    evaluator_version: str
    family: str
    method: str
    label: str | None
    score: float | None = None
    confidence: float | None = None
    severity: str | None = "low"
    review_status: str = "PASSED"
    evidence: list[EvidenceItem] = field(default_factory=list)
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


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

