from dataclasses import dataclass, field
from typing import Optional

from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn


@dataclass
class GoldenCallLabel:
    call_id: str
    what_happened: str
    correct_outcome: str
    facts_customer_gave: str = ""
    sentiment: str = "Neutral"
    emotion: str = "Neutral"
    overall: str = "Good"
    first_thing_wrong_line: Optional[int] = None
    first_thing_wrong_what: Optional[str] = None
    first_thing_wrong_category: Optional[str] = None
    first_thing_wrong_description: Optional[str] = None
    never_rule_broken: str = "None"
    interaction_id: Optional[str] = None
    reviewer_notes: Optional[str] = None
    conversation_status: Optional[str] = None
    language_slice: Optional[str] = None


@dataclass
class GoldenEvaluationInput:
    interaction: InteractionEnvelope
    turns: list[TranscriptTurn]


@dataclass
class GoldenDatasetRecord:
    label: GoldenCallLabel
    test_flag: bool | None = None
    input_hash: str | None = None
    evaluation_input: GoldenEvaluationInput | None = None
    error: str | None = None


@dataclass
class GoldenDataset:
    dataset_hash: str
    records: list[GoldenDatasetRecord] = field(default_factory=list)
