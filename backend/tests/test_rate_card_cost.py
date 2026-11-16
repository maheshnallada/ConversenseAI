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
    stt_cost = manager.calculate_stt_cost(audio_s=60.0, provider="pulse")
    assert stt_cost is not None
    assert round(stt_cost, 4) == 0.006

    # Telephony cost: 120s at $0.01 / min = $0.02
    line_cost = manager.calculate_telephony_cost(connected_s=120.0, channel="phone")
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


def test_model_rate_matching_requires_an_exact_configured_model():
    manager = RateCardManager()

    assert manager.calculate_llm_cost(
        "unrelated-gemini-3.5-flash-lite",
        input_tokens=1000,
        output_tokens=1000,
    ) is None
    assert manager.calculate_llm_cost(
        "gemini-3.5-flash-lite-unpriced",
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
        tts_model="bulbul:v3",
        stt_provider="pulse",
        telephony_channel="phone",
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
def test_invalid_rate_card_shapes_are_unavailable(tmp_path, invalid_data):
    import json

    config_path = tmp_path / "invalid-rates.json"
    config_path.write_text(json.dumps(invalid_data), encoding="utf-8")

    manager = RateCardManager(config_path)

    assert manager.is_valid is False
    assert manager.calculate_llm_cost(
        "gemini-3.5-flash-lite", input_tokens=1000, output_tokens=1000
    ) is None


def test_rate_card_version_is_exposed():
    manager = RateCardManager()

    assert manager.version == "2026-11-14"


def test_missing_rate_does_not_use_default_provider_or_model(tmp_path):
    import json

    config_path = tmp_path / "partial-rates.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "test-version",
                "currency": "USD",
                "rates": {
                    "llm": {"priced-model": {"input_per_1m": 1, "output_per_1m": 1}},
                    "stt": {},
                    "tts": {},
                    "telephony": {},
                },
            }
        ),
        encoding="utf-8",
    )
    manager = RateCardManager(config_path)

    assert manager.calculate_stt_cost(60.0, provider="unpriced-provider") is None
    assert manager.calculate_tts_cost(60.0, model="unpriced-model") is None
    assert manager.calculate_telephony_cost(60.0, channel="unpriced-channel") is None


def test_total_estimate_is_unavailable_when_a_supplied_component_is_unpriced():
    manager = RateCardManager()

    breakdown = manager.calculate_interaction_cost(
        model_name="gemini-3.5-flash-lite",
        input_tokens=1000,
        output_tokens=1000,
        stt_audio_s=60.0,
        tts_audio_s=None,
        connected_s=None,
        stt_provider=None,
    )

    assert breakdown.llm_cost is not None
    assert breakdown.stt_cost is None
    assert breakdown.total_cost is None


def test_nonfinite_usage_values_are_unavailable():
    manager = RateCardManager()

    assert manager.calculate_stt_cost(float("inf"), provider="pulse") is None
    assert manager.calculate_tts_cost(float("nan"), model="bulbul:v3") is None
    assert manager.calculate_telephony_cost(float("inf"), channel="phone") is None
    assert manager.calculate_llm_cost(
        "gemini-3.5-flash-lite", input_tokens=True, output_tokens=1
    ) is None

