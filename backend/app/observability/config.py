import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CostBreakdown:
    llm_cost: float | None
    stt_cost: float | None
    tts_cost: float | None
    telephony_cost: float | None
    total_cost: float | None
    currency: str = "UNKNOWN"


@dataclass
class ObservabilityConfig:
    currency: str = "USD"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gemini-3.5-flash-lite"

    @classmethod
    def from_env(cls) -> "ObservabilityConfig":
        return cls(
            currency=os.getenv("DEFAULT_CURRENCY", "USD"),
            llm_base_url=os.getenv("LLM_BASE_URL"),
            llm_api_key=os.getenv("LLM_API_KEY"),
            llm_model=os.getenv("LLM_MODEL", "gemini-3.5-flash-lite"),
        )


def _is_positive_finite(value: float | None) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


class RateCardManager:
    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is None:
            # Look in configs/rate_cards.json relative to repository root
            root = Path(__file__).resolve().parent.parent.parent.parent
            config_path = root / "configs" / "rate_cards.json"

        self.config_path = Path(config_path)
        self.config_data = self._load()
        self.is_valid = bool(self.config_data)
        self.version = self.config_data.get("version")
        self.currency = self.config_data.get("currency", "UNKNOWN")
        self.rates = self.config_data.get("rates", {})

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as rate_file:
                config = json.load(rate_file)
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(config, dict):
            return {}
        version = config.get("version")
        currency = config.get("currency")
        rates = config.get("rates")
        if (
            not isinstance(version, str)
            or not version.strip()
            or not isinstance(currency, str)
            or not currency.strip()
            or not isinstance(rates, dict)
        ):
            return {}

        required_fields = {
            "llm": {"input_per_1m", "output_per_1m"},
            "stt": {"per_minute"},
            "tts": {"per_minute"},
            "telephony": {"per_minute"},
        }
        for category, category_rates in rates.items():
            if not isinstance(category_rates, dict):
                return {}
            fields = required_fields.get(category)
            for rate in category_rates.values():
                if not isinstance(rate, dict):
                    return {}
                if fields is not None:
                    if not fields.issubset(rate):
                        return {}
                    values = (rate[field] for field in fields)
                else:
                    values = rate.values()
                if any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < 0
                    for value in values
                ):
                    return {}
        return config

    def calculate_llm_cost(
        self,
        model_name: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> float | None:
        if (
            not model_name
            or not isinstance(input_tokens, int)
            or isinstance(input_tokens, bool)
            or not isinstance(output_tokens, int)
            or isinstance(output_tokens, bool)
        ):
            return None
        if input_tokens < 0 or output_tokens < 0:
            return None

        clean_model = model_name.lower().split("/")[-1].strip()
        llm_rates = self.rates.get("llm", {})
        rate = llm_rates.get(clean_model)
        if not rate:
            return None

        in_rate = rate.get("input_per_1m")
        out_rate = rate.get("output_per_1m")
        if in_rate is None or out_rate is None:
            return None
        in_cost = (input_tokens / 1_000_000.0) * in_rate
        out_cost = (output_tokens / 1_000_000.0) * out_rate
        return round(in_cost + out_cost, 6)

    def calculate_stt_cost(
        self,
        audio_s: float | None,
        provider: str | None = None,
    ) -> float | None:
        if not _is_positive_finite(audio_s) or provider is None:
            return None
        stt_rates = self.rates.get("stt", {})
        rate = stt_rates.get(provider)
        if rate is None or "per_minute" not in rate:
            return None
        cost = (audio_s / 60.0) * rate["per_minute"]
        return round(cost, 6)

    def calculate_tts_cost(
        self,
        audio_s: float | None,
        model: str | None = None,
    ) -> float | None:
        if not _is_positive_finite(audio_s) or model is None:
            return None
        tts_rates = self.rates.get("tts", {})
        rate = tts_rates.get(model)
        if rate is None or "per_minute" not in rate:
            return None
        cost = (audio_s / 60.0) * rate["per_minute"]
        return round(cost, 6)

    def calculate_telephony_cost(
        self,
        connected_s: float | None,
        channel: str | None = None,
    ) -> float | None:
        if not _is_positive_finite(connected_s) or channel is None:
            return None
        phone_rates = self.rates.get("telephony", {})
        rate = phone_rates.get(channel)
        if rate is None or "per_minute" not in rate:
            return None
        cost = (connected_s / 60.0) * rate["per_minute"]
        return round(cost, 6)

    def calculate_interaction_cost(
        self,
        model_name: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        stt_audio_s: float | None,
        tts_audio_s: float | None,
        connected_s: float | None,
        tts_model: str | None = None,
        stt_provider: str | None = None,
        telephony_channel: str | None = None,
    ) -> CostBreakdown:
        llm = self.calculate_llm_cost(model_name, input_tokens, output_tokens)
        stt = self.calculate_stt_cost(stt_audio_s, provider=stt_provider)
        tts = self.calculate_tts_cost(tts_audio_s, model=tts_model)
        tel = self.calculate_telephony_cost(
            connected_s, channel=telephony_channel
        )

        requested_costs = []
        if input_tokens is not None or output_tokens is not None:
            requested_costs.append(llm)
        if stt_audio_s is not None:
            requested_costs.append(stt)
        if tts_audio_s is not None:
            requested_costs.append(tts)
        if connected_s is not None:
            requested_costs.append(tel)
        total = (
            round(sum(requested_costs), 6)
            if requested_costs and all(cost is not None for cost in requested_costs)
            else None
        )

        return CostBreakdown(
            llm_cost=llm,
            stt_cost=stt,
            tts_cost=tts,
            telephony_cost=tel,
            total_cost=total,
            currency=self.currency,
        )

