from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


logger = logging.getLogger(__name__)

# Operational telemetry is an append-only observability log. It is not
# conversational memory and must never block the tutor request path.
TELEMETRY_PATH = Path("data/runtime_telemetry.jsonl")
SCHEMA_VERSION = 2
_telemetry_write_lock = threading.Lock()
TELEMETRY_FIELDS = (
    "schema_version",
    "timestamp",
    "request_id",
    "event",
    "entrypoint",
    "user_scope",
    "route",
    "route_reason",
    "guard_result",
    "guard_reason",
    "skill_id",
    "provider",
    "provider_attempt",
    "model",
    "status",
    "error_category",
    "error_type",
    "fallback",
    "fallback_from",
    "fallback_to",
    "latency_ms",
    "question_length",
    "context_turn_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class RequestTelemetryContext:
    request_id: str
    entrypoint: str
    user_scope: str
    question_length: int
    started_at: float
    validation_recorded: bool = False


_request_context: ContextVar[RequestTelemetryContext | None] = ContextVar(
    "request_telemetry_context",
    default=None,
)
_provider_attempt: ContextVar[int] = ContextVar("request_provider_attempt", default=0)
_request_outcome: ContextVar[tuple[str, str | None]] = ContextVar(
    "request_telemetry_outcome",
    default=("success", None),
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_request_context(
    entrypoint: str,
    *,
    user_scope: str,
    question_length: int = 0,
    request_id: str | None = None,
) -> RequestTelemetryContext:
    return RequestTelemetryContext(
        request_id=request_id or uuid.uuid4().hex,
        entrypoint=entrypoint,
        user_scope=user_scope,
        question_length=max(question_length, 0),
        started_at=time.perf_counter(),
    )


@contextmanager
def activate_request_context(context: RequestTelemetryContext) -> Iterator[None]:
    context_token = _request_context.set(context)
    attempt_token = _provider_attempt.set(0)
    outcome_token = _request_outcome.set(("success", None))
    try:
        yield
    finally:
        _request_outcome.reset(outcome_token)
        _provider_attempt.reset(attempt_token)
        _request_context.reset(context_token)


def current_request_context() -> RequestTelemetryContext | None:
    return _request_context.get()


def with_question_length(
    context: RequestTelemetryContext,
    question_length: int,
) -> RequestTelemetryContext:
    return replace(context, question_length=max(question_length, 0))


def next_provider_attempt() -> int | None:
    if current_request_context() is None:
        return None
    attempt = _provider_attempt.get() + 1
    _provider_attempt.set(attempt)
    return attempt


def mark_request_outcome(status: str, error_category: str | None = None) -> None:
    if current_request_context() is not None:
        _request_outcome.set((status, error_category))


def current_request_outcome() -> tuple[str, str | None]:
    return _request_outcome.get()


def emit_runtime_event(
    event: str,
    *,
    context: RequestTelemetryContext | None = None,
    **fields: Any,
) -> None:
    request_context = context or current_request_context()
    if request_context is None:
        return
    write_runtime_telemetry(
        {
            "schema_version": SCHEMA_VERSION,
            "timestamp": utc_timestamp(),
            "request_id": request_context.request_id,
            "event": event,
            "entrypoint": request_context.entrypoint,
            "user_scope": request_context.user_scope,
            **fields,
        }
    )


def record_request_received(context: RequestTelemetryContext, *, route: str | None = None) -> None:
    emit_runtime_event(
        "request_received",
        context=context,
        status="received",
        route=route,
        question_length=context.question_length,
    )


def record_request_validation(
    context: RequestTelemetryContext,
    *,
    status: str,
    error_category: str | None = None,
) -> RequestTelemetryContext:
    emit_runtime_event(
        "request_validated",
        context=context,
        status=status,
        error_category=error_category,
        question_length=context.question_length,
    )
    return replace(context, validation_recorded=True)


def record_request_terminal(
    context: RequestTelemetryContext,
    *,
    status: str,
    error_category: str | None = None,
) -> None:
    event = "request_failed" if status == "error" else "request_completed"
    emit_runtime_event(
        event,
        context=context,
        status=status,
        error_category=error_category,
        latency_ms=round((time.perf_counter() - context.started_at) * 1000),
    )


def write_runtime_telemetry(record: dict[str, Any], path: Path | None = None) -> None:
    target = path or TELEMETRY_PATH
    safe_record = {field: record.get(field) for field in TELEMETRY_FIELDS}
    if safe_record["timestamp"] is None:
        safe_record["timestamp"] = utc_timestamp()
    line = json.dumps(safe_record, ensure_ascii=False, separators=(",", ":")) + "\n"

    try:
        with _telemetry_write_lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as file:
                file.write(line)
    except Exception:
        logger.exception("Runtime telemetry write failed")


def empty_runtime_telemetry_summary(month: str) -> dict[str, Any]:
    return {
        "month": month,
        "total_requests": 0,
        "success": 0,
        "error": 0,
        "total_tokens": 0,
        "fallback_count": 0,
        "provider_attempts": 0,
        "rejected": 0,
        "by_entrypoint": [],
        "by_provider": [],
        "recent_requests": [],
    }


def aggregate_runtime_telemetry(month: str, path: Path | None = None) -> dict[str, Any]:
    target = path or TELEMETRY_PATH
    summary = empty_runtime_telemetry_summary(month)
    if not target.exists():
        return summary

    by_entrypoint = defaultdict(lambda: {"entrypoint": "", "requests": 0, "tokens": 0})
    by_provider = defaultdict(lambda: {"provider": "", "requests": 0, "tokens": 0, "errors": 0})
    recent_records: list[dict[str, Any]] = []

    for record in read_runtime_telemetry_records(target):
        timestamp = str(record.get("timestamp") or "")
        if not timestamp.startswith(month):
            continue

        if is_v2_record(record):
            aggregate_v2_record(
                record,
                summary=summary,
                by_entrypoint=by_entrypoint,
                by_provider=by_provider,
                recent_records=recent_records,
            )
        else:
            aggregate_v1_record(
                record,
                summary=summary,
                by_entrypoint=by_entrypoint,
                by_provider=by_provider,
                recent_records=recent_records,
            )

    summary["by_entrypoint"] = sorted(by_entrypoint.values(), key=lambda item: item["entrypoint"])
    summary["by_provider"] = sorted(by_provider.values(), key=lambda item: item["provider"])
    summary["recent_requests"] = sorted(
        recent_records,
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )[:20]
    return summary


def is_v2_record(record: dict[str, Any]) -> bool:
    return record.get("schema_version") == SCHEMA_VERSION and isinstance(record.get("event"), str)


def aggregate_v2_record(
    record: dict[str, Any],
    *,
    summary: dict[str, Any],
    by_entrypoint: Any,
    by_provider: Any,
    recent_records: list[dict[str, Any]],
) -> None:
    event = record.get("event")
    status = record.get("status")
    entrypoint = str(record.get("entrypoint") or "unknown")

    if event in {"request_completed", "request_failed"}:
        summary["total_requests"] += 1
        if status == "success":
            summary["success"] += 1
        elif status == "error":
            summary["error"] += 1
        elif status == "rejected":
            summary["rejected"] += 1

        by_entrypoint[entrypoint]["entrypoint"] = entrypoint
        by_entrypoint[entrypoint]["requests"] += 1
        recent_records.append(record)
        return

    if event == "provider_fallback":
        summary["fallback_count"] += 1
        return

    if event not in {"provider_attempted", "provider_attempt"}:
        return

    summary["provider_attempts"] += 1
    tokens = numeric_token_value(record.get("total_tokens"))
    summary["total_tokens"] += tokens
    by_entrypoint[entrypoint]["entrypoint"] = entrypoint
    by_entrypoint[entrypoint]["tokens"] += tokens

    provider = str(record.get("provider") or "unknown")
    by_provider[provider]["provider"] = provider
    by_provider[provider]["requests"] += 1
    by_provider[provider]["tokens"] += tokens
    if status == "error":
        by_provider[provider]["errors"] += 1


def aggregate_v1_record(
    record: dict[str, Any],
    *,
    summary: dict[str, Any],
    by_entrypoint: Any,
    by_provider: Any,
    recent_records: list[dict[str, Any]],
) -> None:
    # v1 had one row per provider call and no request correlation identifier.
    # Preserve its historical counting because fallback rows cannot be safely
    # reconstructed into one user request.
    summary["total_requests"] += 1
    summary["provider_attempts"] += 1
    status = record.get("status")
    if status == "success":
        summary["success"] += 1
    elif status == "error":
        summary["error"] += 1

    tokens = numeric_token_value(record.get("total_tokens"))
    summary["total_tokens"] += tokens
    if record.get("fallback") is True:
        summary["fallback_count"] += 1

    entrypoint = str(record.get("entrypoint") or "unknown")
    by_entrypoint[entrypoint]["entrypoint"] = entrypoint
    by_entrypoint[entrypoint]["requests"] += 1
    by_entrypoint[entrypoint]["tokens"] += tokens

    provider = str(record.get("provider") or "unknown")
    by_provider[provider]["provider"] = provider
    by_provider[provider]["requests"] += 1
    by_provider[provider]["tokens"] += tokens
    if status == "error":
        by_provider[provider]["errors"] += 1
    recent_records.append(record)


def read_runtime_telemetry_records(path: Path) -> list[dict[str, Any]]:
    records = []
    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid runtime telemetry line")
                    continue
                if isinstance(record, dict):
                    records.append(record)
    except FileNotFoundError:
        return []
    except Exception:
        logger.exception("Runtime telemetry read failed")
    return records


def numeric_token_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    return 0
