from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.evaluation.facts import FactsExtractionEvaluator


def _envelope():
    return InteractionEnvelope(
        tenant_id="tenant_facts",
        interaction_id="call_facts",
        schema_version="1.0",
        use_case="health_insurance",
    )


def _customer_turn(text):
    return TranscriptTurn("customer_1", "call_facts", "tenant_facts", 0, "customer", text, text.lower())


def test_explicit_no_policy_takes_precedence_over_company_mention():
    result = FactsExtractionEvaluator().evaluate(
        _envelope(),
        [_customer_turn("I don't have company insurance.")],
    )

    assert result.details["existing_policy"] == "None"


def test_incidental_me_words_do_not_imply_self_needs_cover():
    for text in ("Tell me about cover.", "I need some help."):
        result = FactsExtractionEvaluator().evaluate(_envelope(), [_customer_turn(text)])

        assert "who_needs_cover" not in result.details


def test_explicit_self_beneficiary_is_detected():
    result = FactsExtractionEvaluator().evaluate(
        _envelope(),
        [_customer_turn("I need health insurance for me.")],
    )

    assert result.details["who_needs_cover"] == "Self"


def test_callback_time_is_the_matched_text_not_the_whole_utterance():
    result = FactsExtractionEvaluator().evaluate(
        _envelope(),
        [_customer_turn("Please call me tomorrow afternoon.")],
    )

    assert result.details["callback_time"] == "tomorrow"
