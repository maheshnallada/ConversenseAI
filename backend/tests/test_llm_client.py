import asyncio
from types import SimpleNamespace
from typing import get_type_hints

import pytest
from openai import APITimeoutError, LengthFinishReasonError, RateLimitError
from pydantic import BaseModel, ValidationError

import app.evaluation.llm_client as llm_client_module
from app.evaluation.errors import (
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)
from app.evaluation.llm_client import LLMClient, complete_structured


def test_chat_completion_return_annotation_resolves():
    assert get_type_hints(LLMClient.chat_completion)["return"] == str | BaseModel | None


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


def _mock_async_sdk_client(monkeypatch, *, parsed=None, choices=None, error=None):
    captured = {}

    class AsyncCompletions:
        async def parse(self, **kwargs):
            captured["operation"] = "parse"
            captured["request"] = kwargs
            if error:
                raise error
            return SimpleNamespace(
                choices=choices
                if choices is not None
                else [
                    SimpleNamespace(
                        message=SimpleNamespace(parsed=parsed, refusal=None)
                    )
                ]
            )

    class AsyncSDKClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.beta = SimpleNamespace(
                chat=SimpleNamespace(
                    completions=AsyncCompletions(),
                )
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(llm_client_module, "AsyncOpenAI", AsyncSDKClient)
    return captured


class StructuredResponse(BaseModel):
    answer: str


def _configure_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "gateway-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.portkey.ai/v1")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("LLM_PROVIDER", "groq")


def test_async_structured_call_requires_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_PROVIDER", "test-provider")

    with pytest.raises(LLMConfigurationError) as error:
        asyncio.run(complete_structured([], StructuredResponse))

    assert error.value.model == "test-model"
    assert error.value.provider == "test-provider"
    assert "test-model" in str(error.value)


def test_async_structured_call_uses_async_sdk_parse(monkeypatch):
    _configure_llm(monkeypatch)
    expected = StructuredResponse(answer="ok")
    captured = _mock_async_sdk_client(monkeypatch, parsed=expected)

    result = asyncio.run(
        complete_structured(
            [{"role": "user", "content": "hello"}],
            StructuredResponse,
        )
    )

    assert result == expected
    assert captured["operation"] == "parse"
    assert captured["client"]["api_key"] == "gateway-secret"
    assert captured["client"]["base_url"] == "https://api.portkey.ai/v1"
    assert captured["client"]["default_headers"]["x-portkey-provider"] == "@groq"
    assert captured["request"]["response_format"] is StructuredResponse


@pytest.mark.parametrize(
    "provider_error",
    [
        APITimeoutError(request=SimpleNamespace()),
        RateLimitError(
            "rate limit for gateway-secret",
            response=SimpleNamespace(
                status_code=429,
                request=SimpleNamespace(),
                headers={},
            ),
            body={"message": "rate limit for gateway-secret"},
        ),
    ],
)
def test_async_provider_errors_are_typed_and_redacted(monkeypatch, provider_error):
    _configure_llm(monkeypatch)
    _mock_async_sdk_client(monkeypatch, error=provider_error)

    with pytest.raises(LLMRequestError) as error:
        asyncio.run(complete_structured([], StructuredResponse))

    assert error.value.model == "openai/gpt-oss-120b"
    assert error.value.provider == "groq"
    assert error.value.retryable is True
    assert "gateway-secret" not in str(error.value)


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(choices=[]),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        parsed={"unexpected": "shape"},
                        refusal=None,
                    )
                )
            ]
        ),
    ],
)
def test_async_empty_or_malformed_response_is_typed(monkeypatch, response):
    _configure_llm(monkeypatch)
    captured = _mock_async_sdk_client(monkeypatch, choices=response.choices)

    with pytest.raises(LLMResponseError) as error:
        asyncio.run(complete_structured([], StructuredResponse))

    assert error.value.model == "openai/gpt-oss-120b"
    assert error.value.provider == "groq"
    assert captured["operation"] == "parse"


def test_async_sdk_schema_parse_error_is_typed(monkeypatch):
    _configure_llm(monkeypatch)
    with pytest.raises(ValidationError) as validation_error:
        StructuredResponse.model_validate({"unexpected": "shape"})
    _mock_async_sdk_client(monkeypatch, error=validation_error.value)

    with pytest.raises(LLMResponseError):
        asyncio.run(complete_structured([], StructuredResponse))


def test_async_truncated_structured_response_is_typed(monkeypatch):
    _configure_llm(monkeypatch)
    error = LengthFinishReasonError(completion=SimpleNamespace(usage=None))
    _mock_async_sdk_client(monkeypatch, error=error)

    with pytest.raises(LLMResponseError, match="truncated"):
        asyncio.run(complete_structured([], StructuredResponse))


def test_async_structured_call_retries_with_error_context_on_validation_error(monkeypatch):
    _configure_llm(monkeypatch)
    attempts = 0
    captured_messages = []

    class AsyncCompletions:
        async def parse(self, *, messages, response_format, **_kwargs):
            nonlocal attempts
            attempts += 1
            captured_messages.append(list(messages))
            if attempts == 1:
                with pytest.raises(ValidationError) as exc:
                    StructuredResponse.model_validate({"wrong_field": 123})
                raise exc.value
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            parsed=StructuredResponse(answer="corrected"),
                            refusal=None,
                            content='{"answer": "corrected"}',
                        )
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            )

    class AsyncSDKClient:
        def __init__(self, **_kwargs):
            self.beta = SimpleNamespace(chat=SimpleNamespace(completions=AsyncCompletions()))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(llm_client_module, "AsyncOpenAI", AsyncSDKClient)

    completion = asyncio.run(
        llm_client_module.complete_structured_with_usage(
            [{"role": "user", "content": "give answer"}],
            StructuredResponse,
        )
    )

    assert attempts == 2
    assert completion.result.answer == "corrected"
    assert len(captured_messages) == 2
    assert len(captured_messages[1]) > len(captured_messages[0])
    retry_user_msg = captured_messages[1][-1]
    assert retry_user_msg["role"] == "user"
    assert "structured output schema validation" in retry_user_msg["content"]
    assert "Field 'answer'" in retry_user_msg["content"]


def test_async_provider_network_errors_do_not_add_error_context_to_messages(monkeypatch):
    _configure_llm(monkeypatch)
    captured = _mock_async_sdk_client(
        monkeypatch,
        error=APITimeoutError(request=SimpleNamespace()),
    )

    with pytest.raises(LLMRequestError) as error:
        asyncio.run(complete_structured([{"role": "user", "content": "original prompt"}], StructuredResponse))

    assert error.value.retryable is True
    assert captured["request"]["messages"] == [{"role": "user", "content": "original prompt"}]
