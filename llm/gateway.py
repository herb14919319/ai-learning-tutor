"""Shared LLM access: provider clients, invocation, fallback, usage telemetry.

Extracted verbatim from main.py (R1); main.py re-exports these names for
compatibility. Behaviour is unchanged: the per-entrypoint provider comes from
models.resolve_model_provider via active_model_provider, Gemini and DeepSeek
fall back to OpenAI once on retryable errors, and every attempt is recorded in
runtime telemetry.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import TimeoutError
from contextvars import ContextVar
from urllib.error import HTTPError, URLError

from models import DEFAULT_MODEL_PROVIDER, create_model_client
from models.clients import (
    ModelClient,
    ModelClientConfig,
    model_client_config_for_provider,
    model_client_config_from_env,
)
from runtime_telemetry import (
    current_request_context,
    emit_runtime_event,
    mark_request_outcome,
    next_provider_attempt,
    utc_timestamp,
    write_runtime_telemetry,
)


# Fallback warnings keep their pre-R1 logger name so production log identity is unchanged.
logger = logging.getLogger("main")

MODEL_RATE_LIMIT_FALLBACK_RESPONSE = "The model is temporarily busy. Please try again later."

MODEL_CONFIG: ModelClientConfig | None = None
MODEL_PROVIDER = DEFAULT_MODEL_PROVIDER
MODEL_NAME = ""
OPENAI_MODEL = ""
model_clients: dict[str, ModelClient | None] = {}
model_client: ModelClient | None = None
openai_client: ModelClient | None = None
_active_model_provider: ContextVar[str | None] = ContextVar("active_model_provider", default=None)
_active_entrypoint: ContextVar[str | None] = ContextVar("active_entrypoint", default=None)
active_model_provider = _active_model_provider
active_entrypoint = _active_entrypoint


def configure_from_env() -> None:
    """Read provider configuration and build clients; main.py calls this after load_dotenv()."""
    global MODEL_CONFIG, MODEL_PROVIDER, MODEL_NAME, OPENAI_MODEL, model_clients, model_client, openai_client
    MODEL_CONFIG = model_client_config_from_env()
    MODEL_PROVIDER = MODEL_CONFIG.provider or DEFAULT_MODEL_PROVIDER
    MODEL_NAME = MODEL_CONFIG.model
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", MODEL_NAME)
    model_clients = {}
    model_client = create_model_client(MODEL_CONFIG)
    openai_client = create_model_client(model_client_config_for_provider("openai"))


def _ensure_configured() -> None:
    if MODEL_CONFIG is None:
        configure_from_env()


def create_default_client() -> ModelClient | None:
    """A fresh client for the MODEL_PROVIDER env default: no fallback, no telemetry.

    For callers that intentionally bypass ask_gpt (content review, source review,
    the unconfigured Hung-yi skill fallback); their behaviour is unchanged.
    """
    return create_model_client()


def get_model_client(model_provider: str):
    global openai_client
    _ensure_configured()
    provider = (model_provider or MODEL_PROVIDER).strip().lower()
    if provider == "openai":
        if not openai_client and os.getenv("OPENAI_API_KEY", ""):
            openai_client = create_model_client(model_client_config_for_provider("openai"))
        return openai_client
    if provider == MODEL_PROVIDER and model_client:
        return model_client
    if provider not in model_clients:
        model_clients[provider] = create_model_client(model_client_config_for_provider(provider))
    return model_clients[provider]


def ask_gpt(system_prompt: str, user_prompt: str) -> str:
    _ensure_configured()
    provider = _active_model_provider.get() or MODEL_PROVIDER
    client = get_model_client(provider)
    if not client:
        raise RuntimeError(f"{provider} model API is not configured")

    try:
        return complete_model_call(provider, client, system_prompt, user_prompt)
    except Exception as exc:
        if provider not in {"gemini", "deepseek"} or not is_retryable_provider_error(exc):
            raise
        return fallback_to_openai(provider, system_prompt, user_prompt, exc)


def complete_model_call(
    provider: str,
    client,
    system_prompt: str,
    user_prompt: str,
    *,
    fallback: bool = False,
    fallback_from: str | None = None,
) -> str:
    started_at = time.perf_counter()
    provider_attempt = next_provider_attempt()
    if hasattr(client, "last_usage"):
        client.last_usage = None

    try:
        result = client.complete(system_prompt, user_prompt)
    except Exception as exc:
        record_model_call_telemetry(
            provider=provider,
            client=client,
            status="error",
            error_type=type(exc).__name__,
            error_category=categorize_provider_error(exc),
            fallback=fallback,
            fallback_from=fallback_from,
            started_at=started_at,
            provider_attempt=provider_attempt,
        )
        raise

    result_status = "success"
    error_category = None
    if result is None or (isinstance(result, str) and not result.strip()):
        result_status = "error"
        error_category = "provider_invalid_response"
        mark_request_outcome("error", error_category)
    record_model_call_telemetry(
        provider=provider,
        client=client,
        status=result_status,
        error_type=None,
        error_category=error_category,
        fallback=fallback,
        fallback_from=fallback_from,
        started_at=started_at,
        provider_attempt=provider_attempt,
    )
    return result


def record_model_call_telemetry(
    *,
    provider: str,
    client,
    status: str,
    error_type: str | None,
    error_category: str | None,
    fallback: bool,
    fallback_from: str | None,
    started_at: float,
    provider_attempt: int | None,
) -> None:
    usage = normalize_model_usage(getattr(client, "last_usage", None))
    request_context = current_request_context()
    if request_context is not None:
        emit_runtime_event(
            "provider_attempted",
            status=status,
            provider=provider,
            provider_attempt=provider_attempt,
            model=getattr(client, "model", model_client_config_for_provider(provider).model),
            error_category=error_category,
            fallback=fallback,
            fallback_from=fallback_from,
            latency_ms=round((time.perf_counter() - started_at) * 1000),
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
        )
        if status == "error":
            emit_runtime_event(
                "provider_failed",
                status="error",
                provider=provider,
                provider_attempt=provider_attempt,
                model=getattr(client, "model", model_client_config_for_provider(provider).model),
                error_category=error_category,
                latency_ms=round((time.perf_counter() - started_at) * 1000),
            )
        return

    write_runtime_telemetry(
        {
            "timestamp": utc_timestamp(),
            "entrypoint": _active_entrypoint.get() or "test",
            "provider": provider,
            "model": getattr(client, "model", model_client_config_for_provider(provider).model),
            "status": status,
            "error_type": error_type,
            "fallback": fallback,
            "fallback_from": fallback_from,
            "latency_ms": round((time.perf_counter() - started_at) * 1000),
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "total_tokens": usage["total_tokens"],
        }
    )


def normalize_model_usage(usage) -> dict:
    if not isinstance(usage, dict):
        usage = {}
    return {
        "input_tokens": usage.get("input_tokens") if isinstance(usage.get("input_tokens"), int) else None,
        "output_tokens": usage.get("output_tokens") if isinstance(usage.get("output_tokens"), int) else None,
        "total_tokens": usage.get("total_tokens") if isinstance(usage.get("total_tokens"), int) else None,
    }


def categorize_provider_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        if error.code == 401 or error.code == 403:
            return "provider_auth_error"
        if error.code == 429:
            return "provider_rate_limit"
        if 500 <= error.code <= 599:
            return "provider_server_error"
    if isinstance(error, TimeoutError):
        return "provider_timeout"
    if isinstance(error, URLError):
        return "provider_network_error"
    return "internal_error"


def is_retryable_provider_error(error: Exception) -> bool:
    if isinstance(error, HTTPError):
        return error.code == 429 or 500 <= error.code <= 599
    return isinstance(error, (URLError, TimeoutError))


def fallback_to_openai(
    original_provider: str,
    system_prompt: str,
    user_prompt: str,
    error: Exception,
) -> str:
    fallback_provider = "openai"
    emit_runtime_event(
        "provider_fallback",
        status="selected",
        fallback_from=original_provider,
        fallback_to=fallback_provider,
        error_category=categorize_provider_error(error),
    )
    fallback_client = get_model_client(fallback_provider)
    status_code = getattr(error, "code", None)
    if not fallback_client:
        mark_request_outcome("error", categorize_provider_error(error))
        logger.warning(
            "Model provider fallback unavailable original_provider=%s fallback_provider=%s status_code=%s",
            original_provider,
            fallback_provider,
            status_code,
        )
        return MODEL_RATE_LIMIT_FALLBACK_RESPONSE

    logger.warning(
        "Model provider fallback original_provider=%s fallback_provider=%s status_code=%s",
        original_provider,
        fallback_provider,
        status_code,
    )
    try:
        return complete_model_call(
            fallback_provider,
            fallback_client,
            system_prompt,
            user_prompt,
            fallback=True,
            fallback_from=original_provider,
        )
    except Exception as fallback_error:
        mark_request_outcome("error", categorize_provider_error(fallback_error))
        logger.exception(
            "Model provider fallback failed original_provider=%s fallback_provider=%s status_code=%s",
            original_provider,
            fallback_provider,
            status_code,
        )
        return MODEL_RATE_LIMIT_FALLBACK_RESPONSE


def fallback_from_gemini_rate_limit(system_prompt: str, user_prompt: str, error: HTTPError) -> str:
    """Backward-compatible wrapper for the original Gemini 429 fallback helper."""
    return fallback_to_openai("gemini", system_prompt, user_prompt, error)
