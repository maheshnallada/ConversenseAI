import json
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
    currency: str = "USD"


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


class RateCardManager:
    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is None:
            # Look in configs/rate_cards.json relative to repository root
            root = Path(__file__).resolve().parent.parent.parent.parent
            config_path = root / "configs" / "rate_cards.json"

        self.config_path = Path(config_path)
        self.config_data = self._load()
        self.currency = self.config_data.get("currency", "USD")
        self.rates = self.config_data.get("rates", {})

    def _load(self) -> dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Fallback default rates
        return {
            "currency": "USD",
            "rates": {
                "llm": {
                    "gemini-3.5-flash-lite": {"input_per_1m": 0.075, "output_per_1m": 0.30},
                    "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
                },
                "stt": {"pulse": {"per_minute": 0.006}},
                "tts": {"bulbul:v3": {"per_minute": 0.015}, "lightning-v3.1": {"per_minute": 0.015}},
                "telephony": {"phone": {"per_minute": 0.01}},
            },
        }

    def calculate_llm_cost(
        self,
        model_name: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> float | None:
        if not model_name or input_tokens is None or output_tokens is None:
            return None

        clean_model = model_name.lower().split("/")[-1].strip()
        llm_rates = self.rates.get("llm", {})

        rate = llm_rates.get(clean_model)
        if not rate:
            # Check prefix match
            for k, v in llm_rates.items():
                if k in clean_model:
                    rate = v
                    break

        if not rate:
            return None

        in_cost = (input_tokens / 1_000_000.0) * rate.get("input_per_1m", 0.0)
        out_cost = (output_tokens / 1_000_000.0) * rate.get("output_per_1m", 0.0)
        return round(in_cost + out_cost, 6)

    def calculate_stt_cost(
        self,
        audio_s: float | None,
        provider: str = "pulse",
    ) -> float | None:
        if audio_s is None or audio_s <= 0:
            return None
        stt_rates = self.rates.get("stt", {})
        rate = stt_rates.get(provider) or stt_rates.get("pulse", {"per_minute": 0.006})
        cost = (audio_s / 60.0) * rate.get("per_minute", 0.006)
        return round(cost, 6)

    def calculate_tts_cost(
        self,
        audio_s: float | None,
        model: str = "bulbul:v3",
    ) -> float | None:
        if audio_s is None or audio_s <= 0:
            return None
        tts_rates = self.rates.get("tts", {})
        rate = tts_rates.get(model) or tts_rates.get("bulbul:v3", {"per_minute": 0.015})
        cost = (audio_s / 60.0) * rate.get("per_minute", 0.015)
        return round(cost, 6)

    def calculate_telephony_cost(
        self,
        connected_s: float | None,
        channel: str = "phone",
    ) -> float | None:
        if connected_s is None or connected_s <= 0:
            return None
        phone_rates = self.rates.get("telephony", {})
        rate = phone_rates.get(channel) or phone_rates.get("phone", {"per_minute": 0.01})
        cost = (connected_s / 60.0) * rate.get("per_minute", 0.01)
        return round(cost, 6)

    def calculate_interaction_cost(
        self,
        model_name: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        stt_audio_s: float | None,
        tts_audio_s: float | None,
        connected_s: float | None,
        tts_model: str = "bulbul:v3",
    ) -> CostBreakdown:
        llm = self.calculate_llm_cost(model_name, input_tokens, output_tokens)
        stt = self.calculate_stt_cost(stt_audio_s)
        tts = self.calculate_tts_cost(tts_audio_s, model=tts_model)
        tel = self.calculate_telephony_cost(connected_s)

        parts = [c for c in [llm, stt, tts, tel] if c is not None]
        total = round(sum(parts), 6) if parts else None

        return CostBreakdown(
            llm_cost=llm,
            stt_cost=stt,
            tts_cost=tts,
            telephony_cost=tel,
            total_cost=total,
            currency=self.currency,
        )

