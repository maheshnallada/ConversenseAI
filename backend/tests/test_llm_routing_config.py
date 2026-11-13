import os
import pytest
from app.observability.config import ObservabilityConfig


def test_default_routing_config():
    config = ObservabilityConfig()
    assert config.currency == "USD"
    assert config.llm_model == "gemini-3.5-flash-lite"
    assert config.llm_base_url is None


def test_override_routing_via_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.portkey.ai/v1")
    monkeypatch.setenv("LLM_API_KEY", "pk-test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("DEFAULT_CURRENCY", "USD")

    config = ObservabilityConfig.from_env()
    assert config.llm_base_url == "https://api.portkey.ai/v1"
    assert config.llm_api_key == "pk-test-key"
    assert config.llm_model == "gpt-4o-mini"
    assert config.currency == "USD"

