"""Web Chat channel: synchronous JSON endpoint with validation, per-IP rate limiting and request telemetry.

Unlike the webhook channels there is no signature, dedupe, executor or push:
the reply is generated in the request and returned as {"reply": ...}.
"""

import threading
import time
from typing import Callable

from flask import jsonify, request

from app.responses import ERROR_FALLBACK_RESPONSE, normalize_response
from models import ENTRYPOINT_WEB_CHAT
from runtime_telemetry import (
    RequestTelemetryContext,
    create_request_context,
    record_request_received,
    record_request_terminal,
    record_request_validation,
)


TUTOR_API_MAX_QUESTION_LENGTH = 3000
TUTOR_API_RATE_LIMIT_WINDOW_SECONDS = 60
TUTOR_API_RATE_LIMIT_REQUESTS = 20
web_chat_rate_limits: dict[str, list[float]] = {}
web_chat_rate_limits_lock = threading.Lock()

# Set by init_app(): main.generate_ai_reply, the tutor runtime entry for this channel.
generate_ai_reply: Callable[..., str] | None = None


def begin_external_request(
    entrypoint: str,
    *,
    question_length: int = 0,
    request_id: str | None = None,
    route: str | None = None,
    user_scope: str = "authenticated",
) -> RequestTelemetryContext:
    context = create_request_context(
        entrypoint,
        user_scope=user_scope,
        question_length=question_length,
        request_id=request_id,
    )
    record_request_received(context, route=route)
    return context


def reject_external_request(
    context: RequestTelemetryContext,
    error_category: str,
) -> None:
    context = record_request_validation(context, status="error", error_category=error_category)
    record_request_terminal(context, status="error", error_category=error_category)


def tutor_api_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def web_chat_rate_limit_exceeded(client_ip: str) -> bool:
    return rate_limit_exceeded(web_chat_rate_limits, web_chat_rate_limits_lock, client_ip)


def rate_limit_exceeded(
    rate_limits: dict[str, list[float]],
    rate_limits_lock: threading.Lock,
    client_id: str,
) -> bool:
    now = time.monotonic()
    window_start = now - TUTOR_API_RATE_LIMIT_WINDOW_SECONDS
    with rate_limits_lock:
        timestamps = [ts for ts in rate_limits.get(client_id, []) if ts > window_start]
        if len(timestamps) >= TUTOR_API_RATE_LIMIT_REQUESTS:
            rate_limits[client_id] = timestamps
            return True
        timestamps.append(now)
        rate_limits[client_id] = timestamps
        return False


def web_chat():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}

    raw_message = payload.get("message")
    message = raw_message.strip() if isinstance(raw_message, str) else ""
    telemetry_context = begin_external_request(
        "web_chat",
        question_length=len(message),
        route="/web-chat",
        user_scope="anonymous",
    )
    if not message:
        reject_external_request(telemetry_context, "validation_error")
        return jsonify({"reply": "請先輸入一個想討論的 AI 學習問題。"}), 400
    if len(message) > TUTOR_API_MAX_QUESTION_LENGTH:
        reject_external_request(telemetry_context, "validation_error")
        return jsonify({"reply": "問題內容過長，請縮短後再試。"}), 400

    client_ip = tutor_api_client_ip()
    if web_chat_rate_limit_exceeded(client_ip):
        reject_external_request(telemetry_context, "rate_limit_error")
        return jsonify({"error": "rate_limit_exceeded"}), 429

    if "skill_id" in payload:
        reject_external_request(telemetry_context, "validation_error")
        return jsonify({"error": "unsupported_skill"}), 400

    # Public Web Chat has no authenticated identity. Do not trust a caller-supplied
    # user_id or place unrelated visitors in one shared conversation bucket.
    telemetry_context = record_request_validation(telemetry_context, status="success")
    reply = generate_ai_reply(
        message,
        user_id=None,
        truncate=False,
        entrypoint=ENTRYPOINT_WEB_CHAT,
        request_context=telemetry_context,
    )
    return jsonify({"reply": normalize_response(reply, ERROR_FALLBACK_RESPONSE)})


def init_app(app, *, reply_generator: Callable[..., str]) -> None:
    """Wire the tutor reply function and register the /web-chat route."""
    global generate_ai_reply
    generate_ai_reply = reply_generator
    app.add_url_rule("/web-chat", endpoint="web_chat", view_func=web_chat, methods=["POST"])
