from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

TELEMETRY_PATH = Path("data/runtime_telemetry.jsonl")
TELEMETRY_FIELDS = (
    "timestamp",
    "entrypoint",
    "provider",
    "model",
    "status",
    "error_type",
    "fallback",
    "fallback_from",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "total_tokens",
)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_runtime_telemetry(record: dict[str, Any], path: Path | None = None) -> None:
    target = path or TELEMETRY_PATH
    safe_record = {field: record.get(field) for field in TELEMETRY_FIELDS}
    if safe_record["timestamp"] is None:
        safe_record["timestamp"] = utc_timestamp()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as file:
            file.write(json.dumps(safe_record, ensure_ascii=False, separators=(",", ":")) + "\n")
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
    monthly_records: list[dict[str, Any]] = []

    for record in read_runtime_telemetry_records(target):
        timestamp = str(record.get("timestamp") or "")
        if not timestamp.startswith(month):
            continue

        monthly_records.append(record)
        summary["total_requests"] += 1
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

    summary["by_entrypoint"] = sorted(by_entrypoint.values(), key=lambda item: item["entrypoint"])
    summary["by_provider"] = sorted(by_provider.values(), key=lambda item: item["provider"])
    summary["recent_requests"] = sorted(
        monthly_records,
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )[:20]
    return summary


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
