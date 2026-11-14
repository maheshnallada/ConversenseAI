import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from openai import APIError, AsyncOpenAI, OpenAI
from pydantic import BaseModel, ValidationError

from app.evaluation.errors import (
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StructuredCompletion:
    result: BaseModel
    raw_output: str | None
    input_tokens: int | None
    output_tokens: int | None


def _client_configuration() -> tuple[str, str, str, str, float, dict[str, str]]:
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    provider = os.getenv("LLM_PROVIDER", "").strip().lstrip("@")
    timeout_seconds = 10.0
    headers: dict[str, str] = {}
    if urlparse(base_url).hostname == "api.portkey.ai" and provider:
        headers["x-portkey-provider"] = f"@{provider}"
    if not provider:
        provider = urlparse(base_url).hostname or "unknown"
    return base_url, api_key, model, provider, timeout_seconds, headers


async def complete_structured(
    messages: Sequence[dict[str, str]],
    response_model: type[BaseModel],
) -> BaseModel:
    completion = await complete_structured_with_usage(messages, response_model)
    return completion.result


async def complete_structured_with_usage(
    messages: Sequence[dict[str, str]],
    response_model: type[BaseModel],
) -> StructuredCompletion:
    base_url, api_key, model, provider, timeout_seconds, headers = (
        _client_configuration()
    )
    if not api_key:
        raise LLMConfigurationError(
            "LLM_API_KEY is required",
            model=model,
            provider=provider,
        )

    try:
        async with AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            default_headers=headers,
        ) as client:
            response = await client.beta.chat.completions.parse(
                model=model,
                messages=list(messages),
                temperature=0.0,
                response_format=response_model,
            )
    except APIError as error:
        raise LLMRequestError(
            f"Structured request failed ({type(error).__name__})",
            model=model,
            provider=provider,
            retryable=type(error).__name__
            in {
                "APITimeoutError",
                "APIConnectionError",
                "RateLimitError",
                "InternalServerError",
            },
        ) from None
    except ValidationError:
        raise LLMResponseError(
            "Provider returned invalid structured output",
            model=model,
            provider=provider,
        ) from None

    choices = getattr(response, "choices", None)
    if not choices:
        raise LLMResponseError(
            "Provider returned no structured response choices",
            model=model,
            provider=provider,
        )

    message = getattr(choices[0], "message", None)
    if message is None or getattr(message, "refusal", None):
        raise LLMResponseError(
            "Provider refused or omitted the structured response",
            model=model,
            provider=provider,
        )
    parsed = getattr(message, "parsed", None)
    if parsed is None:
        raise LLMResponseError(
            "Provider returned an empty structured response",
            model=model,
            provider=provider,
        )

    try:
        result = (
            parsed
            if isinstance(parsed, response_model)
            else response_model.model_validate(parsed)
        )
    except ValidationError:
        raise LLMResponseError(
            "Provider returned invalid structured output",
            model=model,
            provider=provider,
        ) from None
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    output_tokens = getattr(usage, "completion_tokens", None) if usage else None
    content = getattr(message, "content", None)
    raw_output = content if isinstance(content, str) else None
    return StructuredCompletion(
        result=result,
        raw_output=raw_output,
        input_tokens=input_tokens if type(input_tokens) is int else None,
        output_tokens=output_tokens if type(output_tokens) is int else None,
    )


class LLMClient:
    """
    OpenAI-compatible client supporting configurable base URL, API key, and model.
    Falls back to deterministic evaluation when the remote request is unavailable.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.provider = (provider or os.getenv("LLM_PROVIDER", "")).strip().lstrip("@")
        self.timeout_seconds = timeout_seconds

    @property
    def is_live_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        response_format: Optional[type[BaseModel]] = None,
    ) -> Optional[Union[str, BaseModel]]:
        """
        Invokes standard OpenAI-compatible /chat/completions endpoint.
        Returns parsed Pydantic output when requested, otherwise the content string.
        """
        if not self.is_live_configured:
            return None

        headers = {}
        if urlparse(self.base_url).hostname == "api.portkey.ai":
            if self.provider:
                headers["x-portkey-provider"] = f"@{self.provider}"

        request_args: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            with OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                default_headers=headers,
            ) as client:
                if response_format is not None:
                    response = client.beta.chat.completions.parse(
                        **request_args,
                        response_format=response_format,
                    )
                    return response.choices[0].message.parsed

                response = client.chat.completions.create(**request_args)
                return response.choices[0].message.content
        except Exception as e:
            error_message = str(e)
            if self.api_key:
                error_message = error_message.replace(self.api_key, "[redacted]")
            logger.warning(
                "LLM call to %s failed (%s). Falling back to heuristic.",
                self.base_url,
                error_message[:1000],
            )
            return None

