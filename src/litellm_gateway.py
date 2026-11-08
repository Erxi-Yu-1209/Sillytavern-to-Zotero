import logging

import httpx
from openai import OpenAI

from .settings import LITELLM_API_KEY, LITELLM_BASE_URL, LITELLM_HEALTH_URL

logger = logging.getLogger(__name__)


class LiteLLMGateway:
    def __init__(self, base_url: str = LITELLM_BASE_URL, api_key: str = LITELLM_API_KEY):
        self.base_url = base_url
        self.api_key = api_key
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def complete(self, model: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 900) -> str:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        message = response.choices[0].message.content if response.choices else ""
        return message or ""


def check_gateway() -> bool:
    try:
        response = httpx.get(LITELLM_HEALTH_URL, timeout=5)
        return response.status_code == 200
    except Exception as exc:
        logger.warning("LiteLLM health check failed: %s", exc)
        return False
