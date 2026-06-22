from __future__ import annotations

import logging
import inspect
from typing import Callable

from skills.registry import configure as configure_skills
from skills.registry import get_skill
from skills.registry import get_runtime
from skills.runtime import SkillRuntime


logger = logging.getLogger(__name__)


class TutorAgent:
    def __init__(self, ask_gpt: Callable[[str, str], str], skill_runtime: SkillRuntime | None = None):
        self.ask_gpt = ask_gpt
        self.skill_runtime = skill_runtime or get_runtime()
        if skill_runtime:
            self.skill_runtime.configure(ask_gpt)
        else:
            configure_skills(ask_gpt)

    def answer(self, user_message: str) -> str:
        request = self.skill_runtime.normalize_request(user_message)
        decision = self.skill_runtime.route(request)
        skill_name = decision.get("skill", "general")

        if skill_name == "general":
            return self._general_teaching_answer(user_message, reason="router_general")

        try:
            skill = (
                get_skill(skill_name)
                if self.skill_runtime is get_runtime()
                else self.skill_runtime.get_skill(skill_name)
            )
        except Exception:
            logger.exception("Skill failed: %s", skill_name)
            return self._general_teaching_answer(user_message, reason="skill_exception")

        if not skill:
            logger.warning("Router selected unknown skill: %s", skill_name)
            return self._general_teaching_answer(user_message, reason="unknown_skill")

        try:
            skill_answer = self._invoke_skill(skill, request)
        except Exception:
            logger.exception("Skill failed: %s", skill_name)
            return self._general_teaching_answer(user_message, reason="skill_exception")

        if not skill_answer:
            logger.warning("Skill returned empty answer: %s", skill_name)
            return self._general_teaching_answer(user_message, reason="empty_skill_answer")

        return skill_answer

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
