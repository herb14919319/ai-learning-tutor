from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_MODEL_PROVIDER = "openai"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


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
        self.model = model
        self._api_key = api_key

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        model = quote(self.model, safe="")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self._api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))

        parts = []
        for candidate in body.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()


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
    if provider == "openai":
        return ModelClientConfig(
            provider=provider,
            model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )
    raise ValueError("MODEL_PROVIDER must be 'openai' or 'gemini'")


def create_model_client(config: ModelClientConfig | None = None) -> ModelClient | None:
    config = config or model_client_config_from_env()
    if not config.api_key:
        return None
    if config.provider == "gemini":
        return GeminiModelClient(api_key=config.api_key, model=config.model)
    return OpenAIModelClient(api_key=config.api_key, model=config.model)
