"""Shared LLM access boundary.

Callers ask through ask_gpt() (provider selection, fallback, telemetry) or, when
they deliberately bypass that policy, create_default_client(). Model clients are
constructed only here and in models/.
"""

from llm.gateway import (
    MODEL_RATE_LIMIT_FALLBACK_RESPONSE,
    active_entrypoint,
    active_model_provider,
    ask_gpt,
    categorize_provider_error,
    configure_from_env,
    create_default_client,
    is_retryable_provider_error,
)
from models import resolve_model_provider

__all__ = [
    "MODEL_RATE_LIMIT_FALLBACK_RESPONSE",
    "active_entrypoint",
    "active_model_provider",
    "ask_gpt",
    "categorize_provider_error",
    "configure_from_env",
    "create_default_client",
    "is_retryable_provider_error",
    "resolve_model_provider",
]
