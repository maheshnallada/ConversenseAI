import pytest
from app.observability.config import RateCardManager


def test_rate_card_cost_calculation():
    manager = RateCardManager()

    # Gemini 3.5 Flash Lite: 1,000,000 input = $0.30, 1,000,000 output = $2.50
    llm_cost = manager.calculate_llm_cost("gemini-3.5-flash-lite", input_tokens=100000, output_tokens=10000)
    # 0.1 * 0.30 = 0.03 + 0.01 * 2.50 = 0.025 -> total = 0.055
    assert llm_cost is not None
    assert round(llm_cost, 4) == 0.055

    # GPT-4o Mini: 1,000,000 input = $0.15, 1,000,000 output = $0.60
    gpt_cost = manager.calculate_llm_cost("gpt-4o-mini", input_tokens=100000, output_tokens=10000)
    # 0.1 * 0.15 = 0.015 + 0.01 * 0.60 = 0.006 -> total = 0.0210
    assert gpt_cost is not None
    assert round(gpt_cost, 4) == 0.0210

    # STT cost: 60s at $0.006 / min = $0.006
    stt_cost = manager.calculate_stt_cost(audio_s=60.0)
    assert stt_cost is not None
    assert round(stt_cost, 4) == 0.006

    # Telephony cost: 120s at $0.01 / min = $0.02
    line_cost = manager.calculate_telephony_cost(connected_s=120.0)
    assert line_cost is not None
    assert round(line_cost, 4) == 0.02


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens"),
    [(-1, 0), (0, -1), (-1, -1)],
)
def test_negative_token_counts_are_rejected(input_tokens, output_tokens):
    manager = RateCardManager()

    assert manager.calculate_llm_cost(
        "gemini-3.5-flash-lite",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    ) is None


def test_zero_token_counts_are_valid():
    manager = RateCardManager()

    assert manager.calculate_llm_cost(
        "gemini-3.5-flash-lite",
        input_tokens=0,
        output_tokens=0,
    ) == 0.0


def test_model_rate_matching_requires_a_prefix():
    manager = RateCardManager()

    assert manager.calculate_llm_cost(
        "unrelated-gemini-3.5-flash-lite",
        input_tokens=1000,
        output_tokens=1000,
    ) is None


def test_rate_card_total_breakdown():
    manager = RateCardManager()
    breakdown = manager.calculate_interaction_cost(
        model_name="gemini-3.5-flash-lite",
        input_tokens=10000,
        output_tokens=1000,
        stt_audio_s=30.0,
        tts_audio_s=25.0,
        connected_s=60.0,
    )
    assert breakdown.total_cost is not None
    assert breakdown.total_cost > 0.0
    assert breakdown.currency == "USD"
    assert breakdown.llm_cost is not None
    assert breakdown.stt_cost is not None
    assert breakdown.tts_cost is not None
    assert breakdown.telephony_cost is not None


@pytest.mark.parametrize(
    "invalid_data",
    [
        [],
        {"rates": []},
        {"rates": {"llm": []}},
    ],
)
def test_invalid_rate_card_shapes_use_fallback(tmp_path, invalid_data):
    import json

    config_path = tmp_path / "invalid-rates.json"
    config_path.write_text(json.dumps(invalid_data), encoding="utf-8")

    manager = RateCardManager(config_path)

    assert manager.rates["llm"]["gemini-3.5-flash-lite"]["input_per_1m"] == 0.30

