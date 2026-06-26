import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

from agents.tutor_agent import TutorAgent
from menu_router import handle_menu_command, is_menu_command
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False
from flask import Flask, abort, jsonify, request, send_from_directory
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
from openai import OpenAI, OpenAIError


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_NAME = "AI Learning 助教"
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_LINE_TEXT_LENGTH = 4500
PROCESSING_MESSAGE = "助教正在努力思考中..."
DEFAULT_FALLBACK_RESPONSE = "抱歉，這個問題我目前可能無法回覆。"
ERROR_FALLBACK_RESPONSE = "抱歉，目前系統發生異常，請稍後再試。"
TIMEOUT_FALLBACK_RESPONSE = "抱歉，目前查詢時間較長，請稍後再試。"
FALLBACK_MESSAGE = DEFAULT_FALLBACK_RESPONSE
AI_REPLY_TIMEOUT_SECONDS = int(os.getenv("AI_REPLY_TIMEOUT_SECONDS", "45"))
PROCESSED_EVENT_TTL_SECONDS = int(os.getenv("PROCESSED_EVENT_TTL_SECONDS", "600"))
BACKGROUND_WORKERS = int(os.getenv("BACKGROUND_WORKERS", "4"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL") or os.getenv("BASE_URL", "")
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

app = Flask(__name__)
app.json.ensure_ascii = False

line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
webhook_executor = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS)
ai_executor = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS)

# In-memory duplicate guard for LINE webhook retries. This is intentionally
# small and process-local; replace with Redis/DB when running multiple instances.
processed_events: dict[str, float] = {}
processed_events_lock = threading.Lock()


def ask_gpt(system_prompt: str, user_prompt: str) -> str:
    if not openai_client:
        raise RuntimeError("OpenAI API is not configured")

    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.output_text.strip()


tutor_agent = TutorAgent(ask_gpt)


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


def normalize_response(answer: str | None, fallback: str = DEFAULT_FALLBACK_RESPONSE) -> str:
    if answer is None:
        logger.warning("AI Tutor returned None response")
        return fallback
    if isinstance(answer, str) and not answer.strip():
        logger.warning("AI Tutor returned empty response")
        return fallback
    return answer


def generate_tutor_answer(user_text: str, *, user_id: str | None = None) -> str:
    if not openai_client:
        raise RuntimeError("OpenAI API is not configured")

    return normalize_response(tutor_agent.answer(user_text, user_id=user_id))


def generate_ai_reply(user_text: str, *, user_id: str | None = None, truncate: bool = True) -> str:
    try:
        reply = generate_tutor_answer(user_text, user_id=user_id)
    except OpenAIError:
        logger.exception("OpenAI API request failed")
        return ERROR_FALLBACK_RESPONSE
    except Exception:
        logger.exception("Unexpected AI Tutor response error")
        return ERROR_FALLBACK_RESPONSE

    if truncate:
        return truncate_for_line(reply)
    return reply


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


def generate_ai_reply_with_timeout(user_text: str, user_id: str | None = None) -> str:
    try:
        future = ai_executor.submit(generate_ai_reply, user_text, user_id=user_id)
        reply = future.result(timeout=AI_REPLY_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("AI Tutor response timed out after %s seconds", AI_REPLY_TIMEOUT_SECONDS)
        return TIMEOUT_FALLBACK_RESPONSE
    except Exception:
        logger.exception("AI Tutor background response failed")
        return ERROR_FALLBACK_RESPONSE

    return normalize_response(reply)


def process_text_message_async(user_text: str, recipient_id: str) -> None:
    try:
        if user_text.lower() == "/help":
            push_text(recipient_id, help_text())
            return

        reply = generate_ai_reply_with_timeout(user_text, user_id=recipient_id)
    except Exception:
        logger.exception("LINE async text processing failed")
        reply = ERROR_FALLBACK_RESPONSE

    push_text(recipient_id, normalize_response(reply))


@app.get("/")
def health_check():
    return f"{APP_NAME} service is running."


@app.get("/test")
def test_mode():
    question = request.args.get("question", "").strip()

    if not question:
        return jsonify({"error": "Missing required query parameter: question"}), 400

    answer = generate_ai_reply(question, truncate=False)
    return jsonify(
        {
            "question": question,
            "answer": answer,
            "model": OPENAI_MODEL,
        }
    )


@app.post("/api/agent/ask")
def agent_ask():
    call_id = uuid.uuid4().hex
    payload = request.get_json(silent=True) or {}
    raw_caller = payload.get("caller") or "unknown"
    caller = raw_caller.strip() if isinstance(raw_caller, str) else str(raw_caller)
    caller = caller or "unknown"

    raw_question = payload.get("question")
    question = raw_question.strip() if isinstance(raw_question, str) else ""
    if not question:
        logger.warning("[AGENT_API] call_in_rejected call_id=%s reason=missing_question", call_id)
        return jsonify(
            {
                "ok": False,
                "error": "missing_question",
                "source_agent": "ai_learning_tutor",
                "call_id": call_id,
            }
        ), 400

    raw_user_id = payload.get("user_id")
    user_id = raw_user_id.strip() if isinstance(raw_user_id, str) and raw_user_id.strip() else None

    logger.info(
        "[AGENT_API] call_in_received call_id=%s caller=%s question=%s",
        call_id,
        caller,
        question,
    )

    try:
        answer = generate_tutor_answer(question, user_id=user_id)
    except Exception as exc:
        logger.exception("[AGENT_API] call_in_error call_id=%s error=%s", call_id, exc)
        return jsonify(
            {
                "ok": False,
                "error": "internal_error",
                "source_agent": "ai_learning_tutor",
                "call_id": call_id,
            }
        ), 500

    logger.info("[AGENT_API] call_in_success call_id=%s caller=%s", call_id, caller)
    return jsonify(
        {
            "ok": True,
            "answer": answer,
            "source_agent": "ai_learning_tutor",
            "handled_by": "tutor_agent",
            "caller": caller,
            "call_id": call_id,
            "confidence": "medium",
        }
    )


@app.get("/assets/<path:filename>")
def asset_file(filename: str):
    return send_from_directory(ASSETS_DIR, filename)


@app.post("/callback")
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


@handler.add(MessageEvent, message=TextMessageContent)
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
                    ASSETS_DIR,
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
