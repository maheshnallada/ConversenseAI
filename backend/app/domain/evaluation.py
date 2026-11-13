from dataclasses import dataclass, field
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

