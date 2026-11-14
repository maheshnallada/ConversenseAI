import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.evaluation.prompts import BATCH_SYSTEM_PROMPTS
from app.evaluation.schemas import (
    ComplianceAppointmentResult,
    ConversationQualityResult,
    ConversationUnderstandingResult,
)
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.evaluation.errors import LLMRequestError
from app.evaluation.registry import EvaluatorRegistry


def _batch_payload(response_model):
    if response_model is ConversationUnderstandingResult:
        return {
            "outcome": {
                "label": "Not interested",
                "evidence_line": 1,
                "quote": "Not interested.",
                "reason": "The customer declined.",
            },
            "customer_facts": [],
            "sentiment": {
                "label": "Neutral",
                "evidence_line": 1,
                "quote": "Not interested.",
                "reason": "No attitude beyond a decline is established.",
            },
            "emotion": {
                "label": "Neutral",
                "evidence_line": 1,
                "quote": "Not interested.",
                "reason": "No distinct emotion is established.",
            },
        }
    if response_model is ConversationQualityResult:
        return {
            "conversation_quality": {
                "dimensions": {
                    name: {
                        "score": 4,
                        "evidence_line": 1,
                        "quote": "Not interested.",
                        "reason": "A concise interaction.",
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
                "score": 4,
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
                "reason": "Not enough data.",
            },
        }
    return {
        "compliance": {
            "rule_results": {
                f"NR00{i}": {
                    "status": "NOT_DETECTED",
                    "evidence_line": None,
                    "quote": "",
                    "reason": "",
                }
                for i in range(1, 7)
            },
            "potential_violations": [],
        },
        "appointment_interpretation": {
            "appointment_type": "NONE",
            "consent_status": "NOT_PRESENT",
            "consent_evidence_line": None,
            "consent_quote": "",
            "agent_proposal_line": None,
            "agent_proposal_quote": "",
            "date_text": None,
            "time_text": None,
            "interpreted_date": None,
            "interpreted_time": None,
            "interpretation_reason": "No appointment discussed.",
        },
    }


def _batch_interaction():
    return InteractionEnvelope(
        tenant_id="tenant-1",
        interaction_id="interaction-1",
        schema_version="1.0",
    )


def _batch_turn():
    return TranscriptTurn(
        turn_id="turn-1",
        interaction_id="interaction-1",
        tenant_id="tenant-1",
        turn_index=1,
        speaker="customer",
        raw_text="Not interested.",
        normalized_text="Not interested.",
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


def test_registry_runs_three_batches_concurrently_and_preserves_partial_failure(
    monkeypatch,
):
    from app.evaluation.registry import EvaluatorRegistry

    active = 0
    max_active = 0
    calls = []

    async def structured_caller(messages, response_model):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        calls.append(response_model)
        try:
            await asyncio.sleep(0.01)
            if response_model is ConversationQualityResult:
                raise LLMRequestError(
                    "provider unavailable",
                    model="test-model",
                    provider="test-provider",
                )
            return response_model.model_validate(_batch_payload(response_model))
        finally:
            active -= 1

    monkeypatch.setenv("LLM_MODEL", "test-model")
    registry = EvaluatorRegistry(structured_caller=structured_caller)

    run = asyncio.run(
        registry.evaluate_batches(
            _batch_interaction(),
            [_batch_turn()],
        )
    )

    assert len(calls) == 3
    assert max_active == 3
    assert {batch.batch_name for batch in run.batches} == {
        "conversation_understanding",
        "conversation_quality",
        "compliance_appointment",
    }
    assert sum(batch.status == "completed" for batch in run.batches) == 2
    failed = next(
        batch for batch in run.batches if batch.batch_name == "conversation_quality"
    )
    assert failed.status == "failed"
    assert failed.error_type == "LLMRequestError"


def test_registry_can_run_only_selected_retry_batches():
    calls = []

    async def structured_caller(messages, response_model):
        calls.append(response_model)
        return response_model.model_validate(_batch_payload(response_model))

    registry = EvaluatorRegistry(structured_caller=structured_caller)
    run = asyncio.run(
        registry.evaluate_batches(
            _batch_interaction(),
            [_batch_turn()],
            batch_names={"conversation_quality"},
        )
    )

    assert calls == [ConversationQualityResult]
    assert [batch.batch_name for batch in run.batches] == ["conversation_quality"]


def test_registry_retries_only_retryable_provider_failures():
    attempts = 0

    async def structured_caller(messages, response_model):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LLMRequestError(
                "temporary provider failure",
                model="test-model",
                provider="test-provider",
                retryable=True,
            )
        return response_model.model_validate(_batch_payload(response_model))

    registry = EvaluatorRegistry(structured_caller=structured_caller)
    run = asyncio.run(
        registry.evaluate_batches(
            _batch_interaction(),
            [_batch_turn()],
            batch_names={"conversation_understanding"},
        )
    )

    assert attempts == 2
    assert run.batches[0].status == "completed"


def test_registry_routes_invalid_evidence_for_review():
    async def structured_caller(messages, response_model):
        payload = _batch_payload(response_model)
        if response_model is ConversationUnderstandingResult:
            payload["sentiment"]["quote"] = "normalized text not in transcript"
        return response_model.model_validate(payload)

    registry = EvaluatorRegistry(structured_caller=structured_caller)
    run = asyncio.run(
        registry.evaluate_batches(
            _batch_interaction(),
            [_batch_turn()],
            batch_names={"conversation_understanding"},
        )
    )

    batch = run.batches[0]
    assert batch.status == "review_required"
    assert batch.review_required is True
    assert batch.validation["evidence_valid"] is False


def test_invalid_evidence_is_not_used_for_the_derived_assessment():
    async def structured_caller(messages, response_model):
        payload = _batch_payload(response_model)
        if response_model is ConversationUnderstandingResult:
            payload["sentiment"]["quote"] = "normalized text not in transcript"
        return response_model.model_validate(payload)

    registry = EvaluatorRegistry(structured_caller=structured_caller)
    run = asyncio.run(
        registry.evaluate_batches(
            _batch_interaction(),
            [_batch_turn()],
        )
    )

    assert run.summary["overall_assessment"] == "Can't tell"
