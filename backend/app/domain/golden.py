from dataclasses import dataclass
from typing import Optional

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
    never_rule_broken: str = "None"
    interaction_id: Optional[str] = None
    reviewer_notes: Optional[str] = None

