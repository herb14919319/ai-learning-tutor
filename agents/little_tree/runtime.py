from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from agents.little_tree.config import EMPTY_INPUT_REPLY
from agents.little_tree.intent import LittleTreeIntent, classify_intent
from agents.little_tree.policy import PolicyDecision, decide_policy
from agents.little_tree.prompts import build_system_prompt, build_user_prompt
from memory.conversation_context import add_turn


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LittleTreeRequestContext:
    user_message: str
    intent: LittleTreeIntent
    policy: PolicyDecision


class LittleTreeRuntime:
    """Deterministic Little Tree pipeline: input -> intent -> policy -> prompt -> LLM."""

    def __init__(self, ask_gpt: Callable[[str, str], str]):
        self._ask_gpt = ask_gpt

    def prepare(self, user_message: str) -> LittleTreeRequestContext | None:
        question = (user_message or "").strip()
        if not question:
            return None

        intent = classify_intent(question)
        policy = decide_policy(question, intent)
        return LittleTreeRequestContext(user_message=question, intent=intent, policy=policy)

    def answer(self, user_message: str, *, user_id: str | None = None) -> str:
        context = self.prepare(user_message)
        if context is None:
            return EMPTY_INPUT_REPLY

        try:
            reply = self._ask_gpt(
                build_system_prompt(),
                build_user_prompt(
                    context.user_message,
                    user_id=user_id,
                    intent=context.intent,
                    policy=context.policy,
                ),
            )
        except Exception:
            logger.exception("LittleTreeRuntime answer failed")
            raise

        add_turn(user_id, user_message, reply)
        return reply
