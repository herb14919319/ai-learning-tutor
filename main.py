import hmac
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from pathlib import Path

from agents.tutor_agent import TutorAgent
from automation.facebook_content_job import JobStatus, ProductionConfigError, run_publish_once
from memory.conversation_context import clear_active_skill
from router_guard import route_learning_boundary
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from models import (
    DEFAULT_MODEL_PROVIDER,
    ENTRYPOINT_API,
    ENTRYPOINT_LINE,
    ENTRYPOINT_MESSENGER,
    ENTRYPOINT_TUTOR,
    ENTRYPOINT_WEB_CHAT,
    normalize_model_provider,
    resolve_model_provider,
)
from app.channels import line as line_channel
from app.channels import messenger as messenger_channel
from app.channels import web_chat as web_chat_channel
from app.channels.line import PROCESSING_MESSAGE, truncate_for_line
from app.responses import (
    APP_NAME,
    DEFAULT_FALLBACK_RESPONSE,
    ERROR_FALLBACK_RESPONSE,
    TIMEOUT_FALLBACK_RESPONSE,
    normalize_response,
)
from app.courses import ChoiceAnswerMessages, register_choice_answer_route
from knowledge_packs import get_pack
from llm import gateway as llm_gateway
from llm.gateway import (  # re-exported for compatibility; implementation lives in llm/
    MODEL_RATE_LIMIT_FALLBACK_RESPONSE,
    _active_entrypoint,
    _active_model_provider,
    ask_gpt,
    categorize_provider_error,
    complete_model_call,
    fallback_from_gemini_rate_limit,
    fallback_to_openai,
    get_model_client,
    is_retryable_provider_error,
    normalize_model_usage,
    record_model_call_telemetry,
)
from runtime_telemetry import (
    RequestTelemetryContext,
    activate_request_context,
    aggregate_runtime_telemetry,
    create_request_context,
    current_request_outcome,
    emit_runtime_event,
    mark_request_outcome,
    record_request_received,
    record_request_terminal,
    record_request_validation,
)
from skills import ipas_ai_application_planner as ipas_ai_skill
from skills import ipas_cybersecurity as ipas_cyber_skill
from skills import ipas_net_zero_planner as ipas_net_zero_skill
from skills import little_tree as little_tree_skill

# Knowledge Pack contract views of the course packages (chat routing stays with skill manifests).
net_zero_pack = get_pack("ipas_net_zero_planner")
ai_planner_pack = get_pack("ipas_ai_application_planner")
cybersecurity_pack = get_pack("ipas_cybersecurity")


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = DEFAULT_FALLBACK_RESPONSE
# The Little Tree chat runtime is retired, but its exit commands are still reachable
# from chat. Keep their reply and telemetry identity unchanged without that runtime.
LEGACY_EXIT_COMMANDS = frozenset({"/離開", "/李教授"})
LEGACY_EXIT_MESSAGE = "已回到一般 AI Tutor（李教授）模式。你可以繼續問 AI、機器學習或生成式 AI 的問題。"
LEGACY_EXIT_ROUTE = "little_tree_companion"
AI_REPLY_TIMEOUT_SECONDS = int(os.getenv("AI_REPLY_TIMEOUT_SECONDS", "45"))
BACKGROUND_WORKERS = int(os.getenv("BACKGROUND_WORKERS", "4"))

# Provider clients live in llm/; build them after load_dotenv() exactly as before.
llm_gateway.configure_from_env()
MODEL_CONFIG = llm_gateway.MODEL_CONFIG
MODEL_PROVIDER = llm_gateway.MODEL_PROVIDER
MODEL_NAME = llm_gateway.MODEL_NAME
OPENAI_MODEL = llm_gateway.OPENAI_MODEL
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
IPAS_NET_ZERO_CARDS_DIR = (
    Path(__file__).resolve().parent
    / "skills"
    / "ipas_net_zero_planner"
    / "cards"
)

app = Flask(__name__)
app.json.ensure_ascii = False
facebook_publish_lock = threading.Lock()

webhook_executor = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS)
ai_executor = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS)


tutor_agent = TutorAgent(ask_gpt)


def generate_tutor_answer(
    user_text: str,
    *,
    user_id: str | None = None,
    entrypoint: str = ENTRYPOINT_TUTOR,
    model_provider: str | None = None,
    request_context: RequestTelemetryContext | None = None,
) -> str:
    telemetry_context = request_context or create_request_context(
        entrypoint,
        user_scope="channel_user" if user_id else "anonymous",
        question_length=len((user_text or "").strip()),
    )
    if request_context is None:
        record_request_received(telemetry_context)
    if not telemetry_context.validation_recorded:
        telemetry_context = record_request_validation(telemetry_context, status="success")

    provider = model_provider or resolve_model_provider(entrypoint)
    provider_token = _active_model_provider.set(provider)
    entrypoint_token = _active_entrypoint.set(entrypoint)
    try:
        with activate_request_context(telemetry_context):
            try:
                answer = _generate_tutor_answer(user_text, user_id=user_id)
            except Exception as exc:
                record_request_terminal(
                    telemetry_context,
                    status="error",
                    error_category=categorize_provider_error(exc),
                )
                raise

            outcome, error_category = current_request_outcome()
            record_request_terminal(
                telemetry_context,
                status=outcome,
                error_category=error_category,
            )
            return answer
    finally:
        _active_entrypoint.reset(entrypoint_token)
        _active_model_provider.reset(provider_token)


def _generate_tutor_answer(user_text: str, *, user_id: str | None = None) -> str:
    normalized_text = (user_text or "").strip()
    if normalized_text in LEGACY_EXIT_COMMANDS:
        emit_runtime_event("guard_evaluated", status="skipped", guard_reason="active_skill_exit")
        emit_runtime_event(
            "route_selected",
            status="success",
            route=LEGACY_EXIT_ROUTE,
            route_reason="active_skill_exit",
        )
        emit_runtime_event("skill_selected", status="success", skill_id=LEGACY_EXIT_ROUTE)
        clear_active_skill(user_id)
        return LEGACY_EXIT_MESSAGE

    guard_result = route_learning_boundary(user_text)
    emit_runtime_event(
        "guard_evaluated",
        status="success" if guard_result.allowed else "rejected",
        guard_result="allowed" if guard_result.allowed else "rejected",
        guard_reason=guard_result.intent,
        error_category=None if guard_result.allowed else "guard_rejected",
    )
    if not guard_result.allowed:
        mark_request_outcome("rejected", "guard_rejected")
        return guard_result.response or DEFAULT_FALLBACK_RESPONSE

    return normalize_response(tutor_agent.answer(user_text, user_id=user_id))


def generate_ai_reply(
    user_text: str,
    *,
    user_id: str | None = None,
    truncate: bool = True,
    entrypoint: str = ENTRYPOINT_TUTOR,
    model_provider: str | None = None,
    request_context: RequestTelemetryContext | None = None,
) -> str:
    try:
        kwargs = {
            "user_id": user_id,
            "entrypoint": entrypoint,
            "model_provider": model_provider,
        }
        if request_context is not None:
            kwargs["request_context"] = request_context
        reply = generate_tutor_answer(user_text, **kwargs)
    except Exception:
        logger.exception("Unexpected AI Tutor response error")
        return ERROR_FALLBACK_RESPONSE

    if truncate:
        return truncate_for_line(reply)
    return reply


def generate_ai_reply_with_timeout(
    user_text: str,
    user_id: str | None = None,
    *,
    entrypoint: str = ENTRYPOINT_LINE,
    model_provider: str | None = None,
) -> str:
    try:
        future = ai_executor.submit(
            generate_ai_reply,
            user_text,
            user_id=user_id,
            entrypoint=entrypoint,
            model_provider=model_provider,
        )
        reply = future.result(timeout=AI_REPLY_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("AI Tutor response timed out after %s seconds", AI_REPLY_TIMEOUT_SECONDS)
        return TIMEOUT_FALLBACK_RESPONSE
    except Exception:
        logger.exception("AI Tutor background response failed")
        return ERROR_FALLBACK_RESPONSE

    return normalize_response(reply)


def generate_tutor_reply(user_id: str, user_text: str) -> str:
    return generate_ai_reply_with_timeout(user_text, user_id=user_id, entrypoint=ENTRYPOINT_LINE)


def generate_messenger_tutor_reply(user_id: str, user_text: str) -> str:
    return generate_ai_reply_with_timeout(user_text, user_id=user_id, entrypoint=ENTRYPOINT_MESSENGER)


# Channel adapters own transport; they reach the tutor only through these functions.
line_channel.init_app(app, reply_generator=generate_tutor_reply, executor=webhook_executor, assets_dir=ASSETS_DIR)
messenger_channel.init_app(app, reply_generator=generate_messenger_tutor_reply, executor=webhook_executor)
web_chat_channel.init_app(app, reply_generator=generate_ai_reply)
handler = line_channel.handler  # re-exported for compatibility


@app.get("/")
def home():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return jsonify(
        {
            "status": "ok",
            "service": "ai-learning-tutor",
            "timestamp": timestamp,
        }
    )


@app.route("/internal/jobs/facebook-publish", methods=["POST"], provide_automatic_options=False)
def trigger_facebook_publish():
    secret = os.getenv("AI_TUTOR_CRON_SECRET", "").strip()
    if not secret:
        return jsonify({"ok": False, "state": "configuration_error"}), 503

    authorization = request.headers.get("Authorization", "")
    parts = authorization.split(" ")
    if (
        len(parts) != 2
        or parts[0] != "Bearer"
        or not parts[1]
        or any(character.isspace() for character in parts[1])
    ):
        return jsonify({"ok": False, "state": "unauthorized"}), 401
    if not hmac.compare_digest(parts[1], secret):
        return jsonify({"ok": False, "state": "unauthorized"}), 401

    if not facebook_publish_lock.acquire(blocking=False):
        return jsonify({"ok": False, "state": "already_running"}), 409
    try:
        result = run_publish_once()
    except ProductionConfigError:
        return jsonify({"ok": False, "state": "configuration_error"}), 503
    except Exception:
        return jsonify({"ok": False, "state": "internal_error"}), 500
    finally:
        facebook_publish_lock.release()

    if result.status is JobStatus.PUBLISHED:
        return jsonify({"ok": True, "state": "published", "published": True, "post_id": result.post_id})
    if result.status is JobStatus.APPROVAL_REQUIRED:
        # Waiting for human approval is a normal outcome; state is the stored approval state.
        body = {"ok": True, "state": result.approval_state or result.status.value, "published": False}
        if result.content_id:
            body["content_id"] = result.content_id
        return jsonify(body)
    if result.status in (JobStatus.REVIEW_REJECTED, JobStatus.REVIEW_UNCERTAIN):
        return jsonify({"ok": True, "state": result.status.value, "published": False})
    status_code = 502 if result.status is JobStatus.PUBLISH_FAILED else 500
    return jsonify({"ok": False, "state": result.status.value, "published": False}), status_code


@app.get("/little-tree")
def little_tree_page():
    return render_template("little_tree.html")


@app.get("/office-ai")
def office_ai_page():
    return render_template("office_ai.html")


def little_tree_api_error(error: str, message: str, status_code: int):
    return jsonify({"ok": False, "error": error, "message": message}), status_code


@app.get("/api/little-tree/categories")
def little_tree_categories():
    try:
        categories = little_tree_skill.get_categories()
    except little_tree_skill.DataUnavailableError:
        logger.warning("Little Tree category content is unavailable")
        return little_tree_api_error(
            "skill_unavailable",
            "分類內容暫時無法載入，請稍後再試。",
            503,
        )
    except Exception:
        logger.exception("Failed to load Little Tree categories")
        return little_tree_api_error(
            "internal_error",
            "分類內容載入失敗，請稍後再試。",
            500,
        )

    return jsonify({"ok": True, "categories": categories})


@app.get("/api/little-tree/categories/parenting/scenarios")
def little_tree_parenting_scenarios():
    try:
        scenarios = little_tree_skill.get_parenting_scenarios()
    except little_tree_skill.DataUnavailableError:
        logger.warning("Little Tree parenting scenario content is unavailable")
        return little_tree_api_error(
            "skill_unavailable",
            "親子情境暫時無法載入，請稍後再試。",
            503,
        )
    except Exception:
        logger.exception("Failed to load Little Tree parenting scenarios")
        return little_tree_api_error(
            "internal_error",
            "親子情境載入失敗，請稍後再試。",
            500,
        )

    return jsonify({"ok": True, "scenarios": scenarios})


@app.get("/ipas")
def ipas_page():
    try:
        course_info = ai_planner_pack.get_course_info()
        chapters = ai_planner_pack.get_chapters()
        questions = ai_planner_pack.list_questions()
    except ai_planner_pack.unavailable_error:
        logger.warning("iPAS AI application planner course materials are unavailable")
        return render_template(
            "ipas.html",
            course_info={},
            chapters=[],
            questions=[],
            error_message="課程教材暫時無法載入，請稍後再試。",
        ), 503
    except Exception:
        logger.exception("Failed to load iPAS AI application planner course page")
        return render_template(
            "ipas.html",
            course_info={},
            chapters=[],
            questions=[],
            error_message="課程載入時發生錯誤，請稍後再試。",
        ), 500

    return render_template(
        "ipas.html",
        course_info=course_info,
        chapters=chapters,
        questions=questions,
        error_message=None,
    )


register_choice_answer_route(
    app,
    "/api/ipas/answer",
    endpoint="ipas_ai_answer",
    pack=ai_planner_pack,
    messages=ChoiceAnswerMessages(
        unavailable="題庫暫時無法使用，請稍後再試。",
        internal_error="批改失敗，請稍後再試。",
        unavailable_log="iPAS AI application planner answer materials are unavailable",
        failure_log="Failed to grade iPAS AI application planner answer",
    ),
    logger=logger,
)


@app.get("/ipas/cybersecurity")
def ipas_cybersecurity_page():
    try:
        chapter_index = cybersecurity_pack.get_chapters()
        return render_template(
            "ipas_cybersecurity.html",
            course_info=cybersecurity_pack.get_course_info(),
            topics=[
                {
                    "chapter": cybersecurity_pack.get_chapter(item["chapter_id"]),
                    "cards": cybersecurity_pack.get_flashcards(item["chapter_id"]),
                    "questions": cybersecurity_pack.get_chapter_questions(item["chapter_id"]),
                }
                for item in chapter_index
            ],
            error_message=None,
        )
    except cybersecurity_pack.unavailable_error:
        logger.warning("iPAS cybersecurity CIA materials are unavailable")
        return render_template(
            "ipas_cybersecurity.html", course_info={}, topics=[],
            error_message="資安教材目前無法載入。",
        ), 503


@app.post("/api/ipas/cybersecurity/answer")
def ipas_cybersecurity_answer():
    payload = request.get_json(silent=True) if request.is_json else None
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "invalid_json", "message": "請提供有效的 JSON 請求。"}), 400
    question_id = payload.get("question_id")
    selected = payload.get("answer")
    if not isinstance(question_id, str) or not question_id.strip():
        return jsonify({"ok": False, "error": "missing_question_id", "message": "缺少 question_id。"}), 400
    if not isinstance(selected, str) or selected.strip().upper() not in {"A", "B", "C", "D"}:
        return jsonify({"ok": False, "error": "invalid_answer", "message": "answer 必須是 A、B、C 或 D。"}), 400
    try:
        return jsonify({"ok": True, **cybersecurity_pack.submit_answer(question_id, selected)})
    except ValueError:
        return jsonify({"ok": False, "error": "question_not_found", "message": "找不到指定的題目。"}), 404
    except cybersecurity_pack.unavailable_error:
        return jsonify({"ok": False, "error": "skill_unavailable", "message": "資安教材目前無法使用。"}), 503


@app.get("/ipas/net-zero-planner")
def ipas_net_zero_page():
    try:
        course_info = net_zero_pack.get_course_info()
        chapter_index = net_zero_pack.get_chapters()
        chapters = [net_zero_pack.get_chapter(item["chapter_id"]) for item in chapter_index]
        questions = net_zero_pack.list_questions()
    except net_zero_pack.unavailable_error:
        logger.warning("iPAS net-zero course materials are unavailable")
        return render_template(
            "ipas_net_zero.html",
            course_info={},
            chapters=[],
            questions=[],
            error_message="淨零碳課程教材目前無法載入，請稍後再試。",
        ), 503
    except Exception:
        logger.exception("Failed to load iPAS net-zero course page")
        return render_template(
            "ipas_net_zero.html",
            course_info={},
            chapters=[],
            questions=[],
            error_message="淨零碳課程目前暫時無法使用，請稍後再試。",
        ), 500

    return render_template(
        "ipas_net_zero.html",
        course_info=course_info,
        chapters=chapters,
        questions=questions,
        error_message=None,
    )


@app.get("/ipas/net-zero-planner/cards/<path:filename>")
def ipas_net_zero_card(filename: str):
    normalized = filename.replace("\\", "/")
    parts = normalized.split("/")
    allowed_chapters = {f"ch{number:02d}" for number in range(1, 9)}
    allowed_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    if (
        len(parts) < 2
        or parts[0] not in allowed_chapters
        or any(part in {"", ".", ".."} for part in parts)
        or Path(parts[-1]).suffix.casefold() not in allowed_extensions
    ):
        abort(404)
    return send_from_directory(IPAS_NET_ZERO_CARDS_DIR, normalized)


register_choice_answer_route(
    app,
    "/api/ipas/net-zero-planner/answer",
    endpoint="ipas_net_zero_answer",
    pack=net_zero_pack,
    messages=ChoiceAnswerMessages(
        unavailable="課程教材目前無法使用，請稍後再試。",
        internal_error="題目批改失敗，請稍後再試。",
        unavailable_log="iPAS net-zero answer materials are unavailable",
        failure_log="Failed to grade iPAS net-zero answer",
    ),
    logger=logger,
)


def require_dashboard_access():
    expected_key = os.getenv("DASHBOARD_API_KEY") or os.getenv("OBSERVABILITY_API_KEY")
    supplied_key = request.headers.get("X-Dashboard-Key", "")
    if not expected_key or not hmac.compare_digest(supplied_key, expected_key):
        abort(403)


@app.get("/dashboard")
def runtime_dashboard():
    month = request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
    return render_template("runtime_observability.html", month=month)


@app.get("/observability")
def observability_dashboard():
    require_dashboard_access()
    month = request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
    return render_template("runtime_observability.html", month=month)


@app.get("/api/runtime/telemetry")
def runtime_telemetry_api():
    require_dashboard_access()
    month = request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
    return jsonify(aggregate_runtime_telemetry(month))


@app.get("/assets/<path:filename>")
def asset_file(filename: str):
    return send_from_directory(ASSETS_DIR, filename)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
