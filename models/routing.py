from __future__ import annotations

import os

from models.clients import DEFAULT_MODEL_PROVIDER


ENTRYPOINT_API = "api"
ENTRYPOINT_LINE = "line"
ENTRYPOINT_MESSENGER = "messenger"
ENTRYPOINT_WEB_CHAT = "web_chat"

DEFAULT_ENTRYPOINT_MODEL_PROVIDERS = {
    ENTRYPOINT_WEB_CHAT: "openai",
    ENTRYPOINT_LINE: "openai",
    ENTRYPOINT_MESSENGER: "openai",
    ENTRYPOINT_API: "openai",
}

ENTRYPOINT_PROVIDER_ENV_VARS = {
    ENTRYPOINT_WEB_CHAT: "WEB_CHAT_MODEL_PROVIDER",
    ENTRYPOINT_LINE: "LINE_MODEL_PROVIDER",
    ENTRYPOINT_MESSENGER: "MESSENGER_MODEL_PROVIDER",
    ENTRYPOINT_API: "API_MODEL_PROVIDER",
}

SUPPORTED_MODEL_PROVIDERS = {"openai", "gemini", "deepseek"}


def supported_model_provider_message() -> str:
    providers = "', '".join(sorted(SUPPORTED_MODEL_PROVIDERS))
    return f"model provider must be one of: '{providers}'"


def normalize_model_provider(provider: str | None) -> str:
    normalized = (provider or DEFAULT_MODEL_PROVIDER).strip().lower()
    if normalized not in SUPPORTED_MODEL_PROVIDERS:
        raise ValueError(supported_model_provider_message())
    return normalized


def resolve_model_provider(entrypoint: str) -> str:
    normalized_entrypoint = (entrypoint or "").strip().lower()
    env_var = ENTRYPOINT_PROVIDER_ENV_VARS.get(normalized_entrypoint)
    default_provider = DEFAULT_ENTRYPOINT_MODEL_PROVIDERS.get(
        normalized_entrypoint,
        os.getenv("MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER),
    )
    configured_provider = os.getenv(env_var, default_provider) if env_var else default_provider
    return normalize_model_provider(configured_provider)
