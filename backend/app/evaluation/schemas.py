from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


OutcomeLabel = Literal[
    "Expert call booked",
    "Call later agreed",
    "Not interested",
    "Do not call",
    "Voicemail",
    "Call screener or machine",
    "No outcome: customer left first",
    "Can't tell",
]
SentimentLabel = Literal["Positive", "Neutral", "Negative", "Can't tell"]
EmotionLabel = Literal[
    "Cooperative",
    "Confused",
    "Frustrated",
    "Disengaged",
    "Neutral",
    "Can't tell",
]
CompletenessStageStatus = Literal[
    "completed", "not_completed", "not_observed", "unknown"
]
ConversationStatus = Literal[
    "COMPLETED",
    "OUTCOME_REACHED_BUT_NOT_CLOSED",
    "CUSTOMER_LEFT_DURING_OPENING",
    "CUSTOMER_LEFT_DURING_DISCUSSION",
    "NO_MEANINGFUL_INTERACTION",
    "MACHINE_OR_VOICEMAIL",
    "UNKNOWN",
]
ComplianceStatus = Literal[
    "DETECTED", "NOT_DETECTED", "REVIEW_REQUIRED", "NOT_EVALUABLE"
]
AppointmentType = Literal["EXPERT_CALL", "CALLBACK", "NONE", "UNCLEAR"]
ConsentStatus = Literal["EXPLICIT", "AMBIGUOUS", "REFUSED", "NOT_PRESENT", "CANT_TELL"]
ContextIssueType = Literal[
    "repeated_question",
    "ignored_information",
    "contradictory_response",
    "irrelevant_followup",
    "poor_objection_handling",
]
NeverRuleId = Literal["NR001", "NR002", "NR003", "NR004", "NR005", "NR006"]
CustomerFactCategory = Literal[
    "existing_insurance",
    "policy_type",
    "coverage_details",
    "location",
    "insurance_requirements",
    "customer_preferences",
    "callback_details",
    "rejection_reason",
    "other_relevant_facts",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceResult(StrictModel):
    evidence_line: int | None = Field(default=None, ge=1)
    quote: str = ""


class OutcomeResult(EvidenceResult):
    label: OutcomeLabel
    reason: str


class SentimentResult(EvidenceResult):
    label: SentimentLabel
    reason: str


class EmotionResult(EvidenceResult):
    label: EmotionLabel
    reason: str


class CustomerFact(StrictModel):
    category: CustomerFactCategory
    field: str
    value: Any
    evidence_line: int = Field(ge=1)
    quote: str = Field(min_length=1)


class ConversationUnderstandingResult(StrictModel):
    outcome: OutcomeResult
    customer_facts: list[CustomerFact]
    sentiment: SentimentResult
    emotion: EmotionResult


class QualityDimension(EvidenceResult):
    score: int | None = Field(default=None, ge=1, le=5)
    reason: str


class QualityDimensions(StrictModel):
    clarity: QualityDimension
    relevance: QualityDimension
    empathy: QualityDimension
    professionalism: QualityDimension
    naturalness: QualityDimension
    responsiveness: QualityDimension
    closing_quality: QualityDimension


class ConversationQuality(StrictModel):
    dimensions: QualityDimensions
    strengths: list[str]
    improvement_areas: list[str]


class ContextAwarenessIssue(StrictModel):
    issue_type: ContextIssueType
    customer_evidence_line: int = Field(ge=1)
    customer_quote: str = Field(min_length=1)
    agent_evidence_line: int = Field(ge=1)
    agent_quote: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    reason: str


class ContextAwarenessDimensions(StrictModel):
    repeated_questions: bool
    ignored_information: bool
    contradictory_responses: bool
    irrelevant_followups: bool
    poor_objection_handling: bool


class ContextAwareness(StrictModel):
    issues: list[ContextAwarenessIssue]
    dimensions: ContextAwarenessDimensions
    score: int | None = Field(default=None, ge=1, le=5)
    first_context_failure_line: int | None = Field(default=None, ge=1)


class CompletenessStage(StrictModel):
    status: CompletenessStageStatus
    evidence_line: int | None = Field(default=None, ge=1)


class CompletenessStages(StrictModel):
    opening: CompletenessStage
    customer_engagement: CompletenessStage
    purpose_explanation: CompletenessStage
    information_collection: CompletenessStage
    outcome_establishment: CompletenessStage
    closing: CompletenessStage


class ConversationCompleteness(StrictModel):
    stages: CompletenessStages
    conversation_status: ConversationStatus
    customer_abandoned: bool | None
    reason: str


class ConversationQualityResult(StrictModel):
    conversation_quality: ConversationQuality
    context_awareness: ContextAwareness
    conversation_completeness: ConversationCompleteness


class ComplianceRuleResult(EvidenceResult):
    status: ComplianceStatus
    reason: str


class ComplianceRules(StrictModel):
    NR001: ComplianceRuleResult
    NR002: ComplianceRuleResult
    NR003: ComplianceRuleResult
    NR004: ComplianceRuleResult
    NR005: ComplianceRuleResult
    NR006: ComplianceRuleResult


class PotentialViolation(StrictModel):
    rule_id: NeverRuleId
    evidence_line: int = Field(ge=1)
    quote: str = Field(min_length=1)
    reason: str


class Compliance(StrictModel):
    rule_results: ComplianceRules
    potential_violations: list[PotentialViolation]


class AppointmentInterpretation(StrictModel):
    appointment_type: AppointmentType
    consent_status: ConsentStatus
    consent_evidence_line: int | None = Field(default=None, ge=1)
    consent_quote: str = ""
    agent_proposal_line: int | None = Field(default=None, ge=1)
    agent_proposal_quote: str = ""
    date_text: str | None = None
    time_text: str | None = None
    interpreted_date: str | None = None
    interpreted_time: str | None = None
    interpretation_reason: str


class ComplianceAppointmentResult(StrictModel):
    compliance: Compliance
    appointment_interpretation: AppointmentInterpretation
