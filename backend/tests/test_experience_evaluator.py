import pytest
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.evaluation.experience import CustomerExperienceEvaluator
from app.evaluation.quality import QualityEvaluator
from app.evaluation.facts import FactsExtractionEvaluator

def _envelope(interaction_id="call_test"):
    return InteractionEnvelope(
        tenant_id="test_tenant",
        interaction_id=interaction_id,
        schema_version="1.0",
        use_case="health_insurance",
    )

def test_sentiment_and_emotion_evaluation():
    evaluator = CustomerExperienceEvaluator()

    turns = [
        TranscriptTurn("t1", "c1", "ten1", 1, "agent", "Hello, how can I help you today?", "hello"),
        TranscriptTurn("t2", "c1", "ten1", 2, "customer", "Stop calling me, you are annoying and I have told you five times!", "stop calling me, you are annoying and i have told you five times!"),
        TranscriptTurn("t3", "c1", "ten1", 3, "agent", "I apologize.", "i apologize.")
    ]

    res = evaluator.evaluate(_envelope("c1"), turns)
    assert res.label == "Negative"
    assert res.details["sentiment"] == "Negative"
    assert res.details["emotion"] == "Frustrated"

def test_cooperative_sentiment_and_emotion():
    evaluator = CustomerExperienceEvaluator()

    turns = [
        TranscriptTurn("t1", "c2", "ten1", 1, "agent", "Hello, calling from PolicyGuru.", "hello"),
        TranscriptTurn("t2", "c2", "ten1", 2, "customer", "Yes sure, I am interested to hear what options you have.", "yes sure, i am interested to hear what options you have.")
    ]

    res = evaluator.evaluate(_envelope("c2"), turns)
    assert res.label == "Positive"
    assert res.details["sentiment"] == "Positive"
    assert res.details["emotion"] == "Cooperative"

def test_quality_and_facts_evaluation():
    quality_eval = QualityEvaluator()
    facts_eval = FactsExtractionEvaluator()

    turns = [
        TranscriptTurn("t1", "c3", "ten1", 1, "agent", "Hello, do you have health insurance?", "hello"),
        TranscriptTurn("t2", "c3", "ten1", 2, "customer", "I currently have company insurance from my employer in Mumbai, looking for cover for my parents.", "i currently have company insurance from my employer in mumbai, looking for cover for my parents."),
        TranscriptTurn("t3", "c3", "ten1", 3, "agent", "Great, let us arrange a consultation tomorrow at 2 PM.", "great")
    ]

    q_res = quality_eval.evaluate(_envelope("c3"), turns)
    assert q_res.label in ["Good", "OK"]

    f_res = facts_eval.evaluate(_envelope("c3"), turns)
    assert f_res.label == "FACTS_EXTRACTED"
    assert "Company" in f_res.details.get("existing_policy", "")
    assert "Parents" in f_res.details.get("who_needs_cover", "")
    assert "Mumbai" in f_res.details.get("city", "")
