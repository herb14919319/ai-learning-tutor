from __future__ import annotations

import logging
import inspect
from contextvars import ContextVar
from typing import Callable

from agents.ai_acronyms import build_ai_acronym_disambiguation_prompt
from memory.conversation_context import add_turn
from memory.conversation_context import build_contextual_prompt
from memory.conversation_context import get_active_skill
from runtime_telemetry import emit_runtime_event
from skills.registry import configure as configure_skills
from skills.registry import get_skill
from skills.registry import get_runtime
from skills.runtime import SkillRuntime


logger = logging.getLogger(__name__)
_active_user_id: ContextVar[str | None] = ContextVar("active_user_id", default=None)
_active_user_message: ContextVar[str | None] = ContextVar("active_user_message", default=None)
LITTLE_TREE_ACTIVE_SKILL = "little_tree_companion"


class TutorAgent:
    def __init__(self, ask_gpt: Callable[[str, str], str], skill_runtime: SkillRuntime | None = None):
        self._ask_gpt = ask_gpt
        self.ask_gpt = self._ask_gpt_with_context
        self.skill_runtime = skill_runtime or get_runtime()
        if skill_runtime:
            self.skill_runtime.configure(self.ask_gpt)
        else:
            configure_skills(self.ask_gpt)

    def _ask_gpt_with_context(self, system_prompt: str, user_prompt: str) -> str:
        acronym_hint = build_ai_acronym_disambiguation_prompt(_active_user_message.get() or "")
        if acronym_hint:
            system_prompt = f"{system_prompt}\n\n{acronym_hint}"
        return self._ask_gpt(
            system_prompt,
            build_contextual_prompt(user_prompt, _active_user_id.get()),
        )

    def answer(self, user_message: str, user_id: str | None = None) -> str:
        _active_user_id.set(user_id)
        _active_user_message.set(user_message)
        request = self.skill_runtime.normalize_request(user_message)
        active_skill = get_active_skill(user_id)
        if active_skill == LITTLE_TREE_ACTIVE_SKILL:
            active_skill = None
        decision = (
            {"skill": active_skill, "reason": "active_skill"}
            if active_skill
            else self.skill_runtime.route(request)
        )
        skill_name = decision.get("skill", "general")
        emit_runtime_event(
            "route_selected",
            status="success",
            route=skill_name,
            route_reason=decision.get("reason"),
        )
        emit_runtime_event("skill_selected", status="success", skill_id=skill_name)

        if skill_name == "general":
            answer = self._general_teaching_answer(user_message, reason="router_general")
            add_turn(user_id, user_message, answer)
            return answer

        try:
            skill = (
                get_skill(skill_name)
                if self.skill_runtime is get_runtime()
                else self.skill_runtime.get_skill(skill_name)
            )
        except Exception:
            logger.exception("Skill failed: %s", skill_name)
            self._record_skill_fallback(skill_name, "skill_exception")
            answer = self._general_teaching_answer(user_message, reason="skill_exception")
            add_turn(user_id, user_message, answer)
            return answer

        if not skill:
            logger.warning("Router selected unknown skill: %s", skill_name)
            self._record_skill_fallback(skill_name, "unknown_skill")
            answer = self._general_teaching_answer(user_message, reason="unknown_skill")
            add_turn(user_id, user_message, answer)
            return answer

        try:
            skill_answer = self._invoke_skill(skill, request)
        except Exception:
            logger.exception("Skill failed: %s", skill_name)
            self._record_skill_fallback(skill_name, "skill_exception")
            answer = self._general_teaching_answer(user_message, reason="skill_exception")
            add_turn(user_id, user_message, answer)
            return answer

        if not skill_answer:
            logger.warning("Skill returned empty answer: %s", skill_name)
            self._record_skill_fallback(skill_name, "empty_skill_answer")
            answer = self._general_teaching_answer(user_message, reason="empty_skill_answer")
            add_turn(user_id, user_message, answer)
            return answer

        add_turn(user_id, user_message, skill_answer)
        return skill_answer

    @staticmethod
    def _record_skill_fallback(skill_name: str, reason: str) -> None:
        emit_runtime_event(
            "skill_selected",
            status="error",
            skill_id=skill_name,
            error_category="skill_unavailable",
        )
        emit_runtime_event(
            "route_selected",
            status="success",
            route="general",
            route_reason=reason,
        )

    def _invoke_skill(self, skill, request) -> str:
        parameters = inspect.signature(skill.answer).parameters
        if len(parameters) <= 1:
            return skill.answer(request.text)
        return skill.answer(request, self.skill_runtime.context)

    def _general_teaching_answer(self, user_message: str, *, reason: str) -> str:
        logger.info("Using general teaching answer: %s", reason)
        system_prompt = """你是 AI Learning 助教。請用一般教學方式回答使用者問題。

回答規則：
- 先講核心直覺，再講細節。
- 先用 black-box 方式說 input、output、目標；需要時再打開機制。
- 不要聲稱自己是任何真實教師或官方服務。
- 不確定的事情要明確說不確定，不要編造來源。
- 使用繁體中文。
"""
        return self.ask_gpt(system_prompt, f"學生問題：{user_message}")
