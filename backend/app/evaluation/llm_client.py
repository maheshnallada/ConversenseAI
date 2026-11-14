import os
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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

