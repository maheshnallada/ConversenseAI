from types import SimpleNamespace

from pydantic import BaseModel

import app.evaluation.llm_client as llm_client_module
from app.evaluation.llm_client import LLMClient


def _mock_sdk_client(monkeypatch, *, parsed=None, content="ok", error=None):
    captured = {}

    def create(**kwargs):
        captured["operation"] = "create"
        captured["request"] = kwargs
        if error:
            raise RuntimeError(error)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    def parse(**kwargs):
        captured["operation"] = "parse"
        captured["request"] = kwargs
        if error:
            raise RuntimeError(error)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
        )

    sdk_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        ),
        beta=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(parse=parse),
            )
        ),
    )

    class ClientContext:
        def __enter__(self):
            return sdk_client

        def __exit__(self, *_args):
            return False

    def create_openai_client(**kwargs):
        captured["client"] = kwargs
        return ClientContext()

    monkeypatch.setattr(llm_client_module, "OpenAI", create_openai_client)
    return captured


def test_structured_response_uses_sdk_parse_with_pydantic_model(monkeypatch):
    class StructuredResponse(BaseModel):
        answer: str

    expected = StructuredResponse(answer="ok")
    captured = _mock_sdk_client(monkeypatch, parsed=expected)

    result = LLMClient(
        base_url="https://api.portkey.ai/v1",
        api_key="gateway-key",
        model="openai/gpt-oss-120b",
    ).chat_completion(
        [{"role": "user", "content": "hello"}],
        response_format=StructuredResponse,
    )

    assert result == expected
    assert captured["operation"] == "parse"
    assert captured["request"]["response_format"] is StructuredResponse
    assert captured["request"]["messages"] == [{"role": "user", "content": "hello"}]


def test_portkey_sdk_request_uses_groq_provider_and_model_id(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    captured = _mock_sdk_client(monkeypatch)

    result = LLMClient(
        base_url="https://api.portkey.ai/v1",
        api_key="gateway-key",
        model="openai/gpt-oss-120b",
        timeout_seconds=4.5,
    ).chat_completion([{"role": "user", "content": "hello"}])

    assert result == "ok"
    assert captured["operation"] == "create"
    assert captured["client"]["base_url"] == "https://api.portkey.ai/v1"
    assert captured["client"]["api_key"] == "gateway-key"
    assert captured["client"]["timeout"] == 4.5
    assert captured["client"]["default_headers"]["x-portkey-provider"] == "@groq"
    assert captured["request"]["model"] == "openai/gpt-oss-120b"
    assert captured["request"]["messages"] == [{"role": "user", "content": "hello"}]


def test_generic_openai_compatible_sdk_request_does_not_add_portkey_header(monkeypatch):
    captured = _mock_sdk_client(monkeypatch)

    LLMClient(
        base_url="https://llm.example/v1",
        api_key="provider-key",
        model="gpt-4o-mini",
    ).chat_completion([{"role": "user", "content": "hello"}])

    assert captured["client"]["api_key"] == "provider-key"
    assert captured["client"]["default_headers"] == {}


def test_sdk_error_logs_response_detail_without_echoing_api_key(monkeypatch, caplog):
    api_key = "gateway-secret"
    _mock_sdk_client(monkeypatch, error=f"route denied token {api_key}")

    result = LLMClient(
        base_url="https://api.portkey.ai/v1",
        api_key=api_key,
        model="openai/gpt-oss-120b",
    ).chat_completion([{"role": "user", "content": "hello"}])

    assert result is None
    assert "route denied" in caplog.text
    assert api_key not in caplog.text
