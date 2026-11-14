import pytest
from pydantic import ValidationError

from app.evaluation.prompts import BATCH_SYSTEM_PROMPTS
from app.evaluation.schemas import (
    ComplianceAppointmentResult,
    ConversationQualityResult,
    ConversationUnderstandingResult,
)


def test_conversation_understanding_accepts_only_design_labels():
    outcome_labels = [
        "Expert call booked",
        "Call later agreed",
        "Not interested",
        "Do not call",
        "Voicemail",
        "Call screener or machine",
        "No outcome: customer left first",
        "Can't tell",
    ]
    sentiment_labels = ["Positive", "Neutral", "Negative", "Can't tell"]
    emotion_labels = [
        "Cooperative",
        "Confused",
        "Frustrated",
        "Disengaged",
        "Neutral",
        "Can't tell",
    ]

    for label in outcome_labels:
        result = ConversationUnderstandingResult.model_validate(
            {
                "outcome": {
                    "label": label,
                    "evidence_line": None,
                    "quote": "",
                    "reason": "Not established.",
                },
                "customer_facts": [],
                "sentiment": {
                    "label": "Can't tell",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "Not established.",
                },
                "emotion": {
                    "label": "Can't tell",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "Not established.",
                },
            }
        )
        assert result.outcome.label == label

    for label in sentiment_labels:
        result = ConversationUnderstandingResult.model_validate(
            {
                "outcome": {
                    "label": "Can't tell",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                },
                "customer_facts": [],
                "sentiment": {
                    "label": label,
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                },
                "emotion": {
                    "label": "Can't tell",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                },
            }
        )
        assert result.sentiment.label == label
        with pytest.raises(ValidationError):
            ConversationUnderstandingResult.model_validate(
                {
                    "outcome": {
                        "label": "Can't tell",
                        "evidence_line": None,
                        "quote": "",
                        "reason": "",
                    },
                    "customer_facts": [],
                    "sentiment": {
                        "label": f"invalid:{label}",
                        "evidence_line": None,
                        "quote": "",
                        "reason": "",
                    },
                    "emotion": {
                        "label": "Can't tell",
                        "evidence_line": None,
                        "quote": "",
                        "reason": "",
                    },
                }
            )

    for label in emotion_labels:
        result = ConversationUnderstandingResult.model_validate(
            {
                "outcome": {
                    "label": "Can't tell",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                },
                "customer_facts": [],
                "sentiment": {
                    "label": "Neutral",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                },
                "emotion": {
                    "label": label,
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                },
            }
        )
        assert result.emotion.label == label
        with pytest.raises(ValidationError):
            ConversationUnderstandingResult.model_validate(
                {
                    "outcome": {
                        "label": "Can't tell",
                        "evidence_line": None,
                        "quote": "",
                        "reason": "",
                    },
                    "customer_facts": [],
                    "sentiment": {
                        "label": "Neutral",
                        "evidence_line": None,
                        "quote": "",
                        "reason": "",
                    },
                    "emotion": {
                        "label": f"invalid:{label}",
                        "evidence_line": None,
                        "quote": "",
                        "reason": "",
                    },
                }
            )


def test_sentiment_and_emotion_reject_each_others_labels():
    payload = {
        "outcome": {
            "label": "Can't tell",
            "evidence_line": None,
            "quote": "",
            "reason": "",
        },
        "customer_facts": [],
        "sentiment": {
            "label": "Cooperative",
            "evidence_line": None,
            "quote": "",
            "reason": "",
        },
        "emotion": {
            "label": "Positive",
            "evidence_line": None,
            "quote": "",
            "reason": "",
        },
    }

    with pytest.raises(ValidationError):
        ConversationUnderstandingResult.model_validate(payload)


def test_quality_schema_accepts_scores_one_to_five_or_null():
    for score in [None, 1, 2, 3, 4, 5]:
        result = ConversationQualityResult.model_validate(
            {
                "conversation_quality": {
                    "dimensions": {
                        name: {
                            "score": score,
                            "evidence_line": None,
                            "quote": "",
                            "reason": "Not observable.",
                        }
                        for name in (
                            "clarity",
                            "relevance",
                            "empathy",
                            "professionalism",
                            "naturalness",
                            "responsiveness",
                            "closing_quality",
                        )
                    },
                    "strengths": [],
                    "improvement_areas": [],
                },
                "context_awareness": {
                    "issues": [],
                    "dimensions": {
                        "repeated_questions": False,
                        "ignored_information": False,
                        "contradictory_responses": False,
                        "irrelevant_followups": False,
                        "poor_objection_handling": False,
                    },
                    "score": score,
                    "first_context_failure_line": None,
                },
                "conversation_completeness": {
                    "stages": {
                        name: {"status": "unknown", "evidence_line": None}
                        for name in (
                            "opening",
                            "customer_engagement",
                            "purpose_explanation",
                            "information_collection",
                            "outcome_establishment",
                            "closing",
                        )
                    },
                    "conversation_status": "UNKNOWN",
                    "customer_abandoned": None,
                    "reason": "Insufficient evidence.",
                },
            }
        )
        assert result.conversation_quality.dimensions.clarity.score == score

    for invalid_score in (0, 6):
        with pytest.raises(ValidationError):
            ConversationQualityResult.model_validate(
                {
                    "conversation_quality": {
                        "dimensions": {
                            name: {
                                "score": invalid_score,
                                "evidence_line": None,
                                "quote": "",
                                "reason": "",
                            }
                            for name in (
                                "clarity",
                                "relevance",
                                "empathy",
                                "professionalism",
                                "naturalness",
                                "responsiveness",
                                "closing_quality",
                            )
                        },
                        "strengths": [],
                        "improvement_areas": [],
                    },
                    "context_awareness": {
                        "issues": [],
                        "dimensions": {
                            "repeated_questions": False,
                            "ignored_information": False,
                            "contradictory_responses": False,
                            "irrelevant_followups": False,
                            "poor_objection_handling": False,
                        },
                        "score": None,
                        "first_context_failure_line": None,
                    },
                    "conversation_completeness": {
                        "stages": {
                            name: {"status": "unknown", "evidence_line": None}
                            for name in (
                                "opening",
                                "customer_engagement",
                                "purpose_explanation",
                                "information_collection",
                                "outcome_establishment",
                                "closing",
                            )
                        },
                        "conversation_status": "UNKNOWN",
                        "customer_abandoned": None,
                        "reason": "",
                    },
                }
            )


def test_completeness_accepts_all_stage_and_conversation_statuses():
    stage_statuses = ["completed", "not_completed", "not_observed", "unknown"]
    conversation_statuses = [
        "COMPLETED",
        "OUTCOME_REACHED_BUT_NOT_CLOSED",
        "CUSTOMER_LEFT_DURING_OPENING",
        "CUSTOMER_LEFT_DURING_DISCUSSION",
        "NO_MEANINGFUL_INTERACTION",
        "MACHINE_OR_VOICEMAIL",
        "UNKNOWN",
    ]
    for stage_status in stage_statuses:
        for conversation_status in conversation_statuses:
            result = ConversationQualityResult.model_validate(
                {
                    "conversation_quality": {
                        "dimensions": {
                            name: {
                                "score": None,
                                "evidence_line": None,
                                "quote": "",
                                "reason": "",
                            }
                            for name in (
                                "clarity",
                                "relevance",
                                "empathy",
                                "professionalism",
                                "naturalness",
                                "responsiveness",
                                "closing_quality",
                            )
                        },
                        "strengths": [],
                        "improvement_areas": [],
                    },
                    "context_awareness": {
                        "issues": [],
                        "dimensions": {
                            "repeated_questions": False,
                            "ignored_information": False,
                            "contradictory_responses": False,
                            "irrelevant_followups": False,
                            "poor_objection_handling": False,
                        },
                        "score": None,
                        "first_context_failure_line": None,
                    },
                    "conversation_completeness": {
                        "stages": {
                            name: {
                                "status": stage_status,
                                "evidence_line": None,
                            }
                            for name in (
                                "opening",
                                "customer_engagement",
                                "purpose_explanation",
                                "information_collection",
                                "outcome_establishment",
                                "closing",
                            )
                        },
                        "conversation_status": conversation_status,
                        "customer_abandoned": None,
                        "reason": "",
                    },
                }
            )
            assert (
                result.conversation_completeness.conversation_status
                == conversation_status
            )


def test_compliance_schema_has_six_rules_and_allowed_statuses():
    rule_statuses = ["DETECTED", "NOT_DETECTED", "REVIEW_REQUIRED", "NOT_EVALUABLE"]
    appointment_types = ["EXPERT_CALL", "CALLBACK", "NONE", "UNCLEAR"]
    consent_statuses = ["EXPLICIT", "AMBIGUOUS", "REFUSED", "NOT_PRESENT", "CANT_TELL"]

    for status in rule_statuses:
        result = ComplianceAppointmentResult.model_validate(
            {
                "compliance": {
                    "rule_results": {
                        f"NR00{i}": {
                            "status": status,
                            "evidence_line": None,
                            "quote": "",
                            "reason": "",
                        }
                        for i in range(1, 7)
                    },
                    "potential_violations": [],
                },
                "appointment_interpretation": {
                    "appointment_type": "UNCLEAR",
                    "consent_status": "CANT_TELL",
                    "consent_evidence_line": None,
                    "consent_quote": "",
                    "agent_proposal_line": None,
                    "agent_proposal_quote": "",
                    "date_text": None,
                    "time_text": None,
                    "interpreted_date": None,
                    "interpreted_time": None,
                    "interpretation_reason": "Unclear.",
                },
            }
        )
        assert len(result.compliance.rule_results.model_dump()) == 6

    for appointment_type in appointment_types:
        for consent_status in consent_statuses:
            result = ComplianceAppointmentResult.model_validate(
                {
                    "compliance": {
                        "rule_results": {
                            f"NR00{i}": {
                                "status": "NOT_EVALUABLE",
                                "evidence_line": None,
                                "quote": "",
                                "reason": "",
                            }
                            for i in range(1, 7)
                        },
                        "potential_violations": [],
                    },
                    "appointment_interpretation": {
                        "appointment_type": appointment_type,
                        "consent_status": consent_status,
                        "consent_evidence_line": None,
                        "consent_quote": "",
                        "agent_proposal_line": None,
                        "agent_proposal_quote": "",
                        "date_text": None,
                        "time_text": None,
                        "interpreted_date": None,
                        "interpreted_time": None,
                        "interpretation_reason": "Unclear.",
                    },
                }
            )
            assert result.appointment_interpretation.appointment_type == appointment_type
            assert result.appointment_interpretation.consent_status == consent_status
            with pytest.raises(ValidationError):
                ComplianceAppointmentResult.model_validate(
                    {
                        "compliance": {
                            "rule_results": {
                                f"NR00{i}": {
                                    "status": "NOT_EVALUABLE",
                                    "evidence_line": None,
                                    "quote": "",
                                    "reason": "",
                                }
                                for i in range(1, 7)
                            },
                            "potential_violations": [],
                        },
                        "appointment_interpretation": {
                            "appointment_type": appointment_type,
                            "consent_status": f"invalid:{consent_status}",
                            "consent_evidence_line": None,
                            "consent_quote": "",
                            "agent_proposal_line": None,
                            "agent_proposal_quote": "",
                            "date_text": None,
                            "time_text": None,
                            "interpreted_date": None,
                            "interpreted_time": None,
                            "interpretation_reason": "",
                        },
                    }
                )


def test_batch_prompts_include_shared_multilingual_rules_once():
    assert set(BATCH_SYSTEM_PROMPTS) == {
        "conversation_understanding",
        "conversation_quality",
        "compliance_appointment",
    }

    for prompt in BATCH_SYSTEM_PROMPTS.values():
        assert prompt.count("MULTILINGUAL RULES:") == 1
        assert "Never translate, normalize, transliterate or correct evidence quotes." in prompt
        assert "Return only the requested JSON structure." in prompt
