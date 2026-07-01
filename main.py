import hmac
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import date, datetime, timezone
from pathlib import Path

from agents.little_tree_agent import (
    EXIT_MESSAGE as LITTLE_TREE_EXIT_MESSAGE,
    LITTLE_TREE_COMMAND,
    LITTLE_TREE_EXIT_COMMANDS,
    LITTLE_TREE_SKILL_NAME,
    WELCOME_MESSAGE as LITTLE_TREE_WELCOME_MESSAGE,
    LittleTreeAgent,
)
from agents.tutor_agent import TutorAgent
from menu_router import handle_menu_command, is_menu_command
from memory.conversation_context import clear_active_skill, get_active_skill, set_active_skill
import messenger_webhook
from router_guard import route_learning_boundary
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
little_tree_agent = LittleTreeAgent(ask_gpt)
SOURCE_AGENT = "ai_learning_tutor"
TUTOR_API_SOURCE = "ai-learning-tutor"
TUTOR_API_MAX_CONTENT_LENGTH = 64 * 1024
TUTOR_API_MAX_QUESTION_LENGTH = 3000
TUTOR_API_RATE_LIMIT_WINDOW_SECONDS = 60
TUTOR_API_RATE_LIMIT_REQUESTS = 20
TUTOR_API_DAILY_QUOTA = 1000
ANSWER_QUESTION_CAPABILITY = "answer_question"
SUPPORTED_AGENT_CAPABILITIES = {ANSWER_QUESTION_CAPABILITY}
tutor_api_rate_limits: dict[str, list[float]] = {}
tutor_api_rate_limits_lock = threading.Lock()
tutor_api_daily_quotas: dict[str, dict[str, int | str]] = {}
tutor_api_daily_quotas_lock = threading.Lock()


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
    normalized_text = (user_text or "").strip()
    if normalized_text == LITTLE_TREE_COMMAND:
        set_active_skill(user_id, LITTLE_TREE_SKILL_NAME)
        return LITTLE_TREE_WELCOME_MESSAGE

    if normalized_text in LITTLE_TREE_EXIT_COMMANDS:
        clear_active_skill(user_id)
        return LITTLE_TREE_EXIT_MESSAGE

    if get_active_skill(user_id) == LITTLE_TREE_SKILL_NAME:
        if not openai_client:
            raise RuntimeError("OpenAI API is not configured")
        return normalize_response(little_tree_agent.answer(user_text, user_id=user_id))

    guard_result = route_learning_boundary(user_text)
    if not guard_result.allowed:
        return guard_result.response or DEFAULT_FALLBACK_RESPONSE

    if not openai_client:
        raise RuntimeError("OpenAI API is not configured")

    return normalize_response(tutor_agent.answer(user_text, user_id=user_id))


def normalize_agent_request(payload: dict) -> dict:
    raw_task = payload.get("task") or ANSWER_QUESTION_CAPABILITY
    task = raw_task.strip() if isinstance(raw_task, str) else str(raw_task)
    task = task or ANSWER_QUESTION_CAPABILITY

    raw_caller = payload.get("caller") or "unknown"
    caller = raw_caller.strip() if isinstance(raw_caller, str) else str(raw_caller)
    caller = caller or "unknown"

    raw_user_id = payload.get("user_id")
    user_id = raw_user_id.strip() if isinstance(raw_user_id, str) and raw_user_id.strip() else None

    input_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    raw_question = input_payload.get("question") if "task" in payload else payload.get("question")
    question = raw_question.strip() if isinstance(raw_question, str) else ""

    return {
        "task": task,
        "caller": caller,
        "user_id": user_id,
        "question": question,
    }


def dispatch_agent_capability(task: str, *, question: str, user_id: str | None = None) -> tuple[str, str]:
    if task not in SUPPORTED_AGENT_CAPABILITIES:
        raise ValueError("unsupported_task")
    if task == ANSWER_QUESTION_CAPABILITY:
        return ANSWER_QUESTION_CAPABILITY, generate_tutor_answer(question, user_id=user_id)
    raise ValueError("unsupported_task")


def normalize_tutor_api_request(payload: dict) -> dict:
    raw_question = payload.get("question")
    question = raw_question.strip() if isinstance(raw_question, str) else ""

    raw_user_id = payload.get("user_id")
    user_id = raw_user_id.strip() if isinstance(raw_user_id, str) and raw_user_id.strip() else None

    raw_source = payload.get("source")
    source = raw_source.strip() if isinstance(raw_source, str) and raw_source.strip() else None

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "question": question,
        "user_id": user_id,
        "source": source,
        "metadata": metadata.copy(),
    }


def authenticate_tutor_api_request() -> tuple[bool, tuple | None]:
    expected_key = os.getenv("AI_TUTOR_API_KEY", "")
    if not expected_key:
        logger.error("AI_TUTOR_API_KEY is not configured; rejecting external tutor API request")
        return False, (jsonify({"ok": False, "error": "server_not_configured"}), 500)

    provided_key = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided_key, expected_key):
        return False, (jsonify({"ok": False, "error": "unauthorized"}), 401)

    return True, None


def tutor_api_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def tutor_api_payload_too_large() -> bool:
    return request.content_length is not None and request.content_length > TUTOR_API_MAX_CONTENT_LENGTH


def tutor_api_rate_limit_exceeded(client_ip: str) -> bool:
    now = time.monotonic()
    window_start = now - TUTOR_API_RATE_LIMIT_WINDOW_SECONDS
    with tutor_api_rate_limits_lock:
        timestamps = [ts for ts in tutor_api_rate_limits.get(client_ip, []) if ts > window_start]
        if len(timestamps) >= TUTOR_API_RATE_LIMIT_REQUESTS:
            tutor_api_rate_limits[client_ip] = timestamps
            return True
        timestamps.append(now)
        tutor_api_rate_limits[client_ip] = timestamps
        return False


def tutor_api_quota_exceeded(api_key: str) -> bool:
    today = date.today().isoformat()
    with tutor_api_daily_quotas_lock:
        quota = tutor_api_daily_quotas.get(api_key)
        if not quota or quota.get("date") != today:
            tutor_api_daily_quotas[api_key] = {"date": today, "count": 0}
            return False
        return int(quota.get("count", 0)) >= TUTOR_API_DAILY_QUOTA


def record_tutor_api_quota_success(api_key: str) -> None:
    today = date.today().isoformat()
    with tutor_api_daily_quotas_lock:
        quota = tutor_api_daily_quotas.get(api_key)
        if not quota or quota.get("date") != today:
            tutor_api_daily_quotas[api_key] = {"date": today, "count": 1}
            return
        quota["count"] = int(quota.get("count", 0)) + 1


def validate_tutor_api_question(payload: dict) -> str | None:
    raw_question = payload.get("question")
    if not isinstance(raw_question, str):
        return None

    question = raw_question.strip()
    if not question or len(question) > TUTOR_API_MAX_QUESTION_LENGTH:
        return None

    return question


def log_tutor_api_audit(
    *,
    started_at: float,
    client_ip: str,
    tutor_request: dict | None,
    question_length: int,
    status_code: int,
) -> None:
    duration_ms = round((time.perf_counter() - started_at) * 1000)
    source = tutor_request.get("source") if tutor_request else None
    user_id = tutor_request.get("user_id") if tutor_request else None
    logger.info(
        "[TUTOR_API_AUDIT] timestamp=%s client_ip=%s source=%s user_id=%s question_length=%s status=%s duration_ms=%s",
        datetime.now(timezone.utc).isoformat(),
        client_ip,
        source,
        user_id,
        question_length,
        status_code,
        duration_ms,
    )


def dispatch_tutor_api_request(tutor_request: dict) -> str:
    return generate_tutor_answer(tutor_request["question"], user_id=tutor_request["user_id"])


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


def generate_tutor_reply(user_id: str, user_text: str) -> str:
    return generate_ai_reply_with_timeout(user_text, user_id=user_id)


def process_text_message_async(user_text: str, recipient_id: str) -> None:
    try:
        if user_text.lower() == "/help":
            push_text(recipient_id, help_text())
            return

        reply = generate_tutor_reply(recipient_id, user_text)
    except Exception:
        logger.exception("LINE async text processing failed")
        reply = ERROR_FALLBACK_RESPONSE

    push_text(recipient_id, normalize_response(reply))


messenger_webhook.configure_messenger_handler(
    reply_generator=generate_tutor_reply,
    executor=webhook_executor,
)


def messenger_enabled() -> bool:
    return os.getenv("MESSENGER_ENABLED", "").strip().lower() == "true"


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
    started_at = time.perf_counter()
    call_id = uuid.uuid4().hex
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    agent_request = normalize_agent_request(payload)
    caller = agent_request["caller"]
    task = agent_request["task"]
    question = agent_request["question"]
    user_id = agent_request["user_id"]
    handled_by = task if task in SUPPORTED_AGENT_CAPABILITIES else None

    logger.info("[AGENT_API] received call_id=%s caller=%s task=%s", call_id, caller, task)

    if task not in SUPPORTED_AGENT_CAPABILITIES:
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        logger.warning(
            "[AGENT_API] rejected call_id=%s caller=%s task=%s handled_by=%s duration_ms=%s reason=unsupported_task",
            call_id,
            caller,
            task,
            handled_by,
            duration_ms,
        )
        return jsonify({"ok": False, "error": "unsupported_task"}), 400

    if not question:
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        logger.warning(
            "[AGENT_API] rejected call_id=%s caller=%s task=%s handled_by=%s duration_ms=%s reason=missing_question",
            call_id,
            caller,
            task,
            handled_by,
            duration_ms,
        )
        return jsonify(
            {
                "ok": False,
                "error": "missing_question",
                "source_agent": SOURCE_AGENT,
                "call_id": call_id,
            }
        ), 400

    logger.info(
        "[AGENT_API] dispatch capability=%s call_id=%s caller=%s task=%s handled_by=%s",
        task,
        call_id,
        caller,
        task,
        handled_by,
    )

    try:
        handled_by, answer = dispatch_agent_capability(task, question=question, user_id=user_id)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started_at) * 1000)
        logger.exception(
            "[AGENT_API] error call_id=%s caller=%s task=%s handled_by=%s duration_ms=%s error=%s",
            call_id,
            caller,
            task,
            handled_by,
            duration_ms,
            exc,
        )
        return jsonify(
            {
                "ok": False,
                "error": "internal_error",
                "source_agent": SOURCE_AGENT,
                "call_id": call_id,
            }
        ), 500

    duration_ms = round((time.perf_counter() - started_at) * 1000)
    logger.info(
        "[AGENT_API] answered call_id=%s caller=%s task=%s handled_by=%s duration_ms=%s",
        call_id,
        caller,
        task,
        handled_by,
        duration_ms,
    )
    return jsonify(
        {
            "ok": True,
            "answer": answer,
            "source_agent": SOURCE_AGENT,
            "handled_by": handled_by,
            "capability": handled_by,
            "caller": caller,
            "call_id": call_id,
            "confidence": "medium",
        }
    )


@app.post("/api/tutor/ask")
def tutor_ask():
    started_at = time.perf_counter()
    client_ip = tutor_api_client_ip()

    if tutor_api_payload_too_large():
        return jsonify({"ok": False, "error": "Payload too large"}), 413

    authenticated, error_response = authenticate_tutor_api_request()
    if not authenticated:
        return error_response

    if tutor_api_rate_limit_exceeded(client_ip):
        status_code = 429
        log_tutor_api_audit(
            started_at=started_at,
            client_ip=client_ip,
            tutor_request=None,
            question_length=0,
            status_code=status_code,
        )
        return jsonify({"ok": False, "error": "Rate limit exceeded"}), status_code

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}

    question = validate_tutor_api_question(payload)
    if question is None:
        tutor_request = normalize_tutor_api_request(payload)
        status_code = 400
        log_tutor_api_audit(
            started_at=started_at,
            client_ip=client_ip,
            tutor_request=tutor_request,
            question_length=0,
            status_code=status_code,
        )
        return jsonify({"ok": False, "error": "Invalid question"}), status_code

    tutor_request = normalize_tutor_api_request(payload)
    api_key = request.headers.get("X-API-Key", "")
    if tutor_api_quota_exceeded(api_key):
        status_code = 403
        log_tutor_api_audit(
            started_at=started_at,
            client_ip=client_ip,
            tutor_request=tutor_request,
            question_length=len(question),
            status_code=status_code,
        )
        return jsonify({"ok": False, "error": "Daily quota exceeded"}), status_code

    try:
        answer = dispatch_tutor_api_request(tutor_request)
    except Exception:
        status_code = 500
        logger.exception(
            "External tutor API request failed source=%s metadata=%s",
            tutor_request["source"],
            tutor_request["metadata"],
        )
        log_tutor_api_audit(
            started_at=started_at,
            client_ip=client_ip,
            tutor_request=tutor_request,
            question_length=len(question),
            status_code=status_code,
        )
        return jsonify({"ok": False, "error": "internal_error"}), status_code

    record_tutor_api_quota_success(api_key)
    status_code = 200
    log_tutor_api_audit(
        started_at=started_at,
        client_ip=client_ip,
        tutor_request=tutor_request,
        question_length=len(question),
        status_code=status_code,
    )
    return jsonify(
        {
            "ok": True,
            "answer": answer,
            "source": TUTOR_API_SOURCE,
        }
    ), status_code


@app.get("/assets/<path:filename>")
def asset_file(filename: str):
    return send_from_directory(ASSETS_DIR, filename)


@app.get("/webhook/messenger")
def messenger_verify():
    if not messenger_enabled():
        abort(404)
    return messenger_webhook.handle_verify_request(request.args, os.getenv("MESSENGER_VERIFY_TOKEN", ""))


@app.post("/webhook/messenger")
def messenger_callback():
    if not messenger_enabled():
        abort(404)

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        messenger_webhook.handle_messenger_event(payload)
    except Exception:
        logger.exception("Messenger webhook handler failed")

    return "OK"


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
