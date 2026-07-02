from __future__ import annotations

from typing import Callable

from agents.little_tree.config import (
    EMPTY_INPUT_REPLY as EMPTY_MESSAGE,
    EXIT_COMMANDS as LITTLE_TREE_EXIT_COMMANDS,
    EXIT_MESSAGE,
    LITTLE_TREE_COMMAND,
    LITTLE_TREE_SKILL_NAME,
    WELCOME_MESSAGE,
)
from agents.little_tree.intent import LittleTreeIntent, classify_intent
from agents.little_tree.prompts import build_system_prompt, build_user_prompt
from agents.little_tree.runtime import LittleTreeRuntime


class LittleTreeAgent:
    """Compatibility facade for the Little Tree runtime."""

    def __init__(self, ask_gpt: Callable[[str, str], str]):
        self._runtime = LittleTreeRuntime(ask_gpt)

    def can_handle(self, user_message: str) -> bool:
        text = (user_message or "").strip().lower()
        if text == LITTLE_TREE_COMMAND or text in LITTLE_TREE_EXIT_COMMANDS:
            return True

        return classify_intent(text) in {
            LittleTreeIntent.LEARNING_QUESTION,
            LittleTreeIntent.PARENT_SUPPORT,
            LittleTreeIntent.TEACHER_SUPPORT,
            LittleTreeIntent.VOLUNTEER_SUPPORT,
            LittleTreeIntent.HOMEWORK_GUIDANCE,
        }

    def answer(self, user_message: str, *, user_id: str | None = None) -> str:
        return self._runtime.answer(user_message, user_id=user_id)
