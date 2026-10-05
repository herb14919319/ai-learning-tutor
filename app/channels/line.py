"""LINE channel: webhook signature check, event dedupe, Rich Menu, reply-token and push messages.

The tutor is reached only through the reply generator main.py passes to
init_app(); this module owns LINE transport concerns only.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from flask import abort, request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from app.channels.line_menu import handle_menu_command, is_menu_command
from app.responses import APP_NAME, DEFAULT_FALLBACK_RESPONSE, ERROR_FALLBACK_RESPONSE, normalize_response


# Logger name kept from pre-R2 (this lived in main.py) so log identity is unchanged.
logger = logging.getLogger("main")

MAX_LINE_TEXT_LENGTH = 4500
PROCESSING_MESSAGE = "助教正在努力思考中..."

# Set by init_app() after main.py has loaded .env, exactly when main.py used to read them.
PROCESSED_EVENT_TTL_SECONDS = 600
PUBLIC_BASE_URL = ""
line_configuration: Configuration | None = None
handler: WebhookHandler | None = None
webhook_executor = None
_reply_generator: Callable[[str, str], str] | None = None
_assets_dir: Path | None = None

# In-memory duplicate guard for LINE webhook retries. This is intentionally
# small and process-local; replace with Redis/DB when running multiple instances.
processed_events: dict[str, float] = {}
processed_events_lock = threading.Lock()


def truncate_for_line(text: str) -> str:
    if len(text) <= MAX_LINE_TEXT_LENGTH:
        return text
    return text[:MAX_LINE_TEXT_LENGTH].rstrip() + "\n\n（回覆已因 LINE 單則訊息長度限制截斷）"


def help_text() -> str:
    return (
        f"你好，我是「{APP_NAME}」。\n\n"
        "你可以直接問我 AI、機器學習、深度學習、Python、AI Agent、RAG、MCP 等問題。\n\n"
        "範例：\n"
        "1. 什麼是 Transformer？\n"
        "2. RAG 跟微調有什麼差別？\n"
        "3. 可以用生活化比喻解釋梯度下降嗎？\n\n"
        "提醒：本服務是 AI 學習工具，非任何教師、學校或教育機構官方帳號。"
    )


def reply_text(reply_token: str, text: str) -> None:
    try:
        with ApiClient(line_configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=truncate_for_line(text))],
                )
            )
    except Exception:
        logger.exception("LINE reply API failed")


def push_text(to: str, text: str) -> None:
    try:
        with ApiClient(line_configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.push_message(
                PushMessageRequest(
                    to=to,
                    messages=[TextMessage(text=truncate_for_line(text))],
                )
            )
    except Exception:
        logger.exception("LINE push API failed")


def public_base_url() -> str:
    if PUBLIC_BASE_URL.strip():
        return PUBLIC_BASE_URL.strip().rstrip("/")
    return request.url_root.rstrip("/")


def line_recipient_id(event: MessageEvent) -> str | None:
    source = getattr(event, "source", None)
    for attr in ("user_id", "group_id", "room_id"):
        value = getattr(source, attr, None)
        if value:
            return value
    return None


def event_deduplication_key(event: MessageEvent) -> str:
    event_id = getattr(event, "webhook_event_id", None)
    message_id = getattr(getattr(event, "message", None), "id", None)
    if event_id:
        return f"event:{event_id}"
    if message_id:
        return f"message:{message_id}"
    return f"reply:{event.reply_token}"


def mark_event_if_new(event: MessageEvent) -> bool:
    now = time.monotonic()
    key = event_deduplication_key(event)
    with processed_events_lock:
        expired_keys = [
            cached_key
            for cached_key, cached_at in processed_events.items()
            if now - cached_at > PROCESSED_EVENT_TTL_SECONDS
        ]
        for cached_key in expired_keys:
            processed_events.pop(cached_key, None)

        if key in processed_events:
            logger.info("Skipping duplicate LINE event: %s", key)
            return False

        processed_events[key] = now
        return True


def process_text_message_async(user_text: str, recipient_id: str) -> None:
    try:
        if user_text.lower() == "/help":
            push_text(recipient_id, help_text())
            return

        reply = _reply_generator(recipient_id, user_text)
    except Exception:
        logger.exception("LINE async text processing failed")
        reply = ERROR_FALLBACK_RESPONSE

    push_text(recipient_id, normalize_response(reply))


def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE signature")
        abort(400)
    except Exception:
        logger.exception("Webhook handler failed")

    return "OK"


def handle_text_message(event: MessageEvent):
    user_text = event.message.text.strip()

    if not mark_event_if_new(event):
        return

    if is_menu_command(user_text):
        try:
            with ApiClient(line_configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                handle_menu_command(
                    user_text,
                    messaging_api,
                    event.reply_token,
                    public_base_url(),
                    _assets_dir,
                )
        except Exception:
            logger.exception("LINE Rich Menu command handling failed")
            reply_text(event.reply_token, DEFAULT_FALLBACK_RESPONSE)
        return

    reply_text(event.reply_token, PROCESSING_MESSAGE)

    recipient_id = line_recipient_id(event)
    if not recipient_id:
        logger.warning("LINE event has no push recipient id")
        return

    try:
        webhook_executor.submit(process_text_message_async, user_text, recipient_id)
    except Exception:
        logger.exception("Failed to submit LINE async processing task")
        push_text(recipient_id, ERROR_FALLBACK_RESPONSE)


def init_app(app, *, reply_generator: Callable[[str, str], str], executor, assets_dir: Path) -> None:
    """Read LINE configuration, register the text-message handler and the /callback route."""
    global PROCESSED_EVENT_TTL_SECONDS, PUBLIC_BASE_URL, line_configuration, handler
    global webhook_executor, _reply_generator, _assets_dir
    PROCESSED_EVENT_TTL_SECONDS = int(os.getenv("PROCESSED_EVENT_TTL_SECONDS", "600"))
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL") or os.getenv("BASE_URL", "")
    line_configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""))
    handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET", ""))
    handler.add(MessageEvent, message=TextMessageContent)(handle_text_message)
    webhook_executor = executor
    _reply_generator = reply_generator
    _assets_dir = assets_dir
    app.add_url_rule("/callback", endpoint="callback", view_func=callback, methods=["POST"])
