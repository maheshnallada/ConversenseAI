import json
import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union
from urllib.parse import urlparse

from openai import APIError, AsyncOpenAI, LengthFinishReasonError, OpenAI
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


def _format_pydantic_validation_error(error: ValidationError) -> str:
    lines = []
    for err in error.errors():
        loc = ".".join(str(item) for item in err.get("loc", []))
        msg = err.get("msg", "Validation error")
        if loc:
            lines.append(f"- Field '{loc}': {msg}")
        else:
            lines.append(f"- {msg}")
    return "\n".join(lines) if lines else f"- {str(error)}"


def _client_configuration() -> tuple[str, str, str, str, float, dict[str, str]]:
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1").strip().rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    provider = os.getenv("LLM_PROVIDER", "").strip().lstrip("@")
    try:
        timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "60.0"))
    except (ValueError, TypeError):
        timeout_seconds = 60.0
    headers: dict[str, str] = {}
    if urlparse(base_url).hostname == "api.portkey.ai" and provider:
        headers["x-portkey-provider"] = f"@{provider}"
        headers["x-portkey-config"] = "pc-entrop-d0ff28"
     

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
    *,
    timeout_seconds: float | None = None,
    max_validation_retries: int = 1,
) -> StructuredCompletion:
    base_url, api_key, model, provider, default_timeout, headers = (
        _client_configuration()
    )
    timeout = timeout_seconds if timeout_seconds is not None else default_timeout
    if not api_key:
        raise LLMConfigurationError(
            "LLM_API_KEY is required",
            model=model,
            provider=provider,
        )

    current_messages = list(messages)
    total_input_tokens = 0
    total_output_tokens = 0
    tokens_tracked = False

    async with AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        default_headers=headers,
    ) as client:
        for attempt in range(max_validation_retries + 1):
            raw_output = None
            try:
                response = await client.beta.chat.completions.parse(
                    model=model,
                    messages=current_messages,
                    # temperature=0.1,
                    response_format=response_model,
                )
            except LengthFinishReasonError:
                raise LLMResponseError(
                    "Provider returned truncated structured output",
                    model=model,
                    provider=provider,
                ) from None
            except APIError as error:
                status_code = getattr(error, "status_code", None)
                err_msg = getattr(error, "message", str(error))
                if api_key:
                    err_msg = err_msg.replace(api_key, "[redacted]")
                logger.error(
                    "LLM structured request failed with APIError (%s, status=%s): %s",
                    type(error).__name__,
                    status_code,
                    err_msg,
                )
                raise LLMRequestError(
                    f"Structured request failed ({type(error).__name__}: {err_msg})",
                    model=model,
                    provider=provider,
                    retryable=type(error).__name__
                    in {
                        "APITimeoutError",
                        "APIConnectionError",
                        "RateLimitError",
                        "InternalServerError",
                    },
                ) from error
            except ValidationError as error:
                if attempt < max_validation_retries:
                    err_msg = _format_pydantic_validation_error(error)
                    logger.warning(
                        "LLM response failed schema validation on attempt %d: %s. Retrying with error context.",
                        attempt + 1,
                        err_msg,
                    )
                    current_messages = list(current_messages)
                    current_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous response failed structured output schema validation with the following error(s):\n"
                                f"{err_msg}\n\n"
                                "Please fix these errors and return a valid JSON object adhering strictly to the schema."
                            ),
                        }
                    )
                    continue
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

            usage = getattr(response, "usage", None)
            if usage:
                inp = getattr(usage, "prompt_tokens", None)
                outp = getattr(usage, "completion_tokens", None)
                if isinstance(inp, int):
                    total_input_tokens += inp
                    tokens_tracked = True
                if isinstance(outp, int):
                    total_output_tokens += outp
                    tokens_tracked = True

            content = getattr(message, "content", None)
            raw_output = content if isinstance(content, str) else None

            parsed = getattr(message, "parsed", None)
            if parsed is None and not content:
                raise LLMResponseError(
                    "Provider returned an empty structured response",
                    model=model,
                    provider=provider,
                )

            try:
                result = (
                    parsed
                    if isinstance(parsed, response_model)
                    else (
                        response_model.model_validate(parsed)
                        if parsed is not None
                        else response_model.model_validate_json(content)
                    )
                )
            except ValidationError as error:
                if attempt < max_validation_retries:
                    err_msg = _format_pydantic_validation_error(error)
                    logger.warning(
                        "Parsed LLM response failed model validation on attempt %d: %s. Retrying with error context.",
                        attempt + 1,
                        err_msg,
                    )
                    current_messages = list(current_messages)
                    if raw_output:
                        current_messages.append(
                            {"role": "assistant", "content": raw_output}
                        )
                    current_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous response failed structured output schema validation with the following error(s):\n"
                                f"{err_msg}\n\n"
                                "Please fix these errors and return a valid JSON object adhering strictly to the schema."
                            ),
                        }
                    )
                    continue
                raise LLMResponseError(
                    "Provider returned invalid structured output",
                    model=model,
                    provider=provider,
                ) from None

            return StructuredCompletion(
                result=result,
                raw_output=raw_output,
                input_tokens=total_input_tokens if tokens_tracked else None,
                output_tokens=total_output_tokens if tokens_tracked else None,
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
        timeout_seconds: Optional[float] = None,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")).strip().rstrip("/")
        self.api_key = (api_key or os.getenv("LLM_API_KEY", "")).strip()
        self.model = (model or os.getenv("LLM_MODEL", "gpt-4o-mini")).strip()
        self.provider = (provider or os.getenv("LLM_PROVIDER", "")).strip().lstrip("@")
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        else:
            try:
                self.timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "60.0"))
            except (ValueError, TypeError):
                self.timeout_seconds = 60.0

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
                    current_messages = list(messages)
                    for attempt in range(2):
                        try:
                            response = client.beta.chat.completions.parse(
                                model=self.model,
                                messages=current_messages,
                                temperature=temperature,
                                response_format=response_format,
                            )
                            parsed = response.choices[0].message.parsed
                            if parsed is not None:
                                return parsed
                            content = getattr(
                                response.choices[0].message, "content", None
                            )
                            if content:
                                return response_format.model_validate_json(content)
                            return None
                        except ValidationError as err:
                            if attempt == 0:
                                err_msg = _format_pydantic_validation_error(err)
                                current_messages = list(current_messages)
                                current_messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "Your previous response failed structured output schema validation with the following error(s):\n"
                                            f"{err_msg}\n\n"
                                            "Please fix these errors and return a valid JSON object adhering strictly to the schema."
                                        ),
                                    }
                                )
                                continue
                            raise

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

