import os
import json
import logging
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Pluggable LLM client supporting configurable base_url, api_key, and model
    (e.g., Bifrost, Portkey, LiteLLM, OpenAI, or direct model providers).
    Provides seamless graceful fallback for deterministic/offline execution.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout_seconds = timeout_seconds

    @property
    def is_live_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Invokes standard OpenAI-compatible /chat/completions endpoint.
        Returns the content string from choice[0].message.content, or None if unavailable/offline.
        """
        if not self.is_live_configured:
            return None

        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status == 200:
                    resp_body = response.read().decode("utf-8")
                    result = json.loads(resp_body)
                    return result.get("choices", [{}])[0].get("message", {}).get("content")
        except Exception as e:
            logger.warning("LLM call to %s failed (%s). Falling back to heuristic.", url, e)
            return None

        return None

