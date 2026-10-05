"""Shared HTTP handling for Knowledge Pack answer APIs.

Only behaviour that was already identical across packs lives here: the
AI Application Planner and Net-Zero Planner answer routes validated, graded
and failed the same way and differed only in two messages and two log lines.
The cybersecurity answer route validates differently and stays pack-specific.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from flask import jsonify, request

from knowledge_packs import KnowledgePack


@dataclass(frozen=True)
class ChoiceAnswerMessages:
    unavailable: str
    internal_error: str
    unavailable_log: str
    failure_log: str


def course_api_error(error: str, message: str, status_code: int):
    return jsonify({"ok": False, "error": error, "message": message}), status_code


def register_choice_answer_route(
    app,
    rule: str,
    *,
    endpoint: str,
    pack: KnowledgePack,
    messages: ChoiceAnswerMessages,
    logger: logging.Logger,
) -> None:
    def view():
        if not request.is_json:
            return course_api_error("invalid_json", "請提供有效的 JSON 請求。", 400)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return course_api_error("invalid_json", "請提供有效的 JSON 請求。", 400)

        raw_question_id = payload.get("question_id")
        question_id = raw_question_id.strip().upper() if isinstance(raw_question_id, str) else ""
        if not question_id:
            return course_api_error("missing_question_id", "缺少 question_id。", 400)

        raw_answer = payload.get("answer")
        answer_value = raw_answer.strip().upper() if isinstance(raw_answer, str) else ""
        if not answer_value:
            return course_api_error("missing_answer", "缺少 answer。", 400)
        if answer_value not in {"A", "B", "C", "D"}:
            return course_api_error("invalid_answer", "answer 必須是 A、B、C 或 D。", 400)

        try:
            result = pack.submit_answer(question_id, answer_value)
        except ValueError:
            return course_api_error("question_not_found", "找不到指定的題目。", 404)
        except pack.unavailable_error:
            logger.warning(messages.unavailable_log)
            return course_api_error("skill_unavailable", messages.unavailable, 503)
        except Exception:
            logger.exception(messages.failure_log)
            return course_api_error("internal_error", messages.internal_error, 500)

        return jsonify({"ok": True, **result})

    view.__name__ = endpoint
    app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=["POST"])
