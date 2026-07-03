from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


DEFAULT_MODEL_PROVIDER = "openai"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

logger = logging.getLogger(__name__)


class ModelClient(Protocol):
    provider: str
    model: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return a text completion for the tutor's system/user prompt pair."""


@dataclass(frozen=True)
class ModelClientConfig:
    provider: str
    model: str
    api_key: str


class OpenAIModelClient:
    provider = "openai"

    def __init__(self, *, api_key: str, model: str = DEFAULT_OPENAI_MODEL):
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(api_key=api_key)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.output_text.strip()


class GeminiModelClient:
    provider = "gemini"

    def __init__(self, *, api_key: str, model: str = DEFAULT_GEMINI_MODEL):
        self.model = normalize_gemini_model_name(model)
        self._api_key = api_key

    def generate_content_url(self) -> str:
        model = quote(self.model, safe="")
        query = urlencode({"key": self._api_key})
        return f"{GEMINI_API_BASE_URL}/models/{model}:generateContent?{query}"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = self.generate_content_url()
        payload = build_gemini_generate_content_payload(system_prompt, user_prompt)
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            logger.error(
                "Gemini API request failed provider=%s model=%s status_code=%s",
                self.provider,
                self.model,
                exc.code,
            )
            raise

        parts = []
        for candidate in body.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()


class DeepSeekModelClient:
    provider = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
    ):
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        self.model = model or DEFAULT_DEEPSEEK_MODEL
        self._api_key = api_key
        self._base_url = normalize_deepseek_base_url(base_url)

    def chat_completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def build_chat_completions_payload(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = self.build_chat_completions_payload(system_prompt, user_prompt)
        request = Request(
            self.chat_completions_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))

        choices = body.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return (message.get("content") or "").strip()


def normalize_deepseek_base_url(base_url: str) -> str:
    return (base_url or DEFAULT_DEEPSEEK_BASE_URL).strip().rstrip("/")


def normalize_gemini_model_name(model: str) -> str:
    normalized = (model or DEFAULT_GEMINI_MODEL).strip()
    if normalized.startswith("models/"):
        normalized = normalized.removeprefix("models/")
    return normalized or DEFAULT_GEMINI_MODEL


def build_gemini_generate_content_payload(system_prompt: str, user_prompt: str) -> dict:
    return {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
    }


def model_client_config_from_env() -> ModelClientConfig:
    provider = os.getenv("MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER).strip().lower()
    return model_client_config_for_provider(provider)


def model_client_config_for_provider(provider: str) -> ModelClientConfig:
    provider = provider.strip().lower()
    if provider == "gemini":
        return ModelClientConfig(
            provider=provider,
            model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            api_key=os.getenv("GEMINI_API_KEY", ""),
        )
    if provider == "deepseek":
        return ModelClientConfig(
            provider=provider,
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        )
    if provider == "openai":
        return ModelClientConfig(
            provider=provider,
            model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )
    raise ValueError("MODEL_PROVIDER must be 'openai', 'gemini', or 'deepseek'")


def create_model_client(config: ModelClientConfig | None = None) -> ModelClient | None:
    config = config or model_client_config_from_env()
    if config.provider == "deepseek" and not config.api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    if not config.api_key:
        return None
    if config.provider == "gemini":
        return GeminiModelClient(api_key=config.api_key, model=config.model)
    if config.provider == "deepseek":
        return DeepSeekModelClient(
            api_key=config.api_key,
            model=config.model,
            base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
        )
    return OpenAIModelClient(api_key=config.api_key, model=config.model)
