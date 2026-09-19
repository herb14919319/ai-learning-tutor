from __future__ import annotations

import os

from models.clients import DEFAULT_MODEL_PROVIDER


ENTRYPOINT_TUTOR = "tutor"
# Compatibility identity for callers that still explicitly identify as the
# retired External Tutor API. Active runtime defaults use ENTRYPOINT_TUTOR.
ENTRYPOINT_API = "api"
ENTRYPOINT_LINE = "line"
ENTRYPOINT_MESSENGER = "messenger"
ENTRYPOINT_WEB_CHAT = "web_chat"

DEFAULT_ENTRYPOINT_MODEL_PROVIDERS = {
    ENTRYPOINT_WEB_CHAT: "openai",
    ENTRYPOINT_LINE: "openai",
    ENTRYPOINT_MESSENGER: "openai",
    ENTRYPOINT_TUTOR: "openai",
    ENTRYPOINT_API: "openai",
}

ENTRYPOINT_PROVIDER_ENV_VARS = {
    ENTRYPOINT_WEB_CHAT: ("WEB_CHAT_MODEL_PROVIDER",),
    ENTRYPOINT_LINE: ("LINE_MODEL_PROVIDER",),
    ENTRYPOINT_MESSENGER: ("MESSENGER_MODEL_PROVIDER",),
    ENTRYPOINT_TUTOR: ("TUTOR_MODEL_PROVIDER", "API_MODEL_PROVIDER"),
    ENTRYPOINT_API: ("API_MODEL_PROVIDER", "TUTOR_MODEL_PROVIDER"),
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
    env_vars = ENTRYPOINT_PROVIDER_ENV_VARS.get(normalized_entrypoint, ())
    default_provider = DEFAULT_ENTRYPOINT_MODEL_PROVIDERS.get(
        normalized_entrypoint,
        os.getenv("MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER),
    )
    configured_provider = default_provider
    for env_var in env_vars:
        if env_var in os.environ:
            configured_provider = os.environ[env_var]
            break
    return normalize_model_provider(configured_provider)
