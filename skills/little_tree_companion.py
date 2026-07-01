from __future__ import annotations

from typing import Callable

from agents.little_tree_agent import EXIT_MESSAGE
from agents.little_tree_agent import LITTLE_TREE_SKILL_NAME
from agents.little_tree_agent import WELCOME_MESSAGE
from agents.little_tree_agent import LittleTreeAgent
from agents.little_tree_agent import build_system_prompt


_ask_gpt: Callable[[str, str], str] | None = None


def configure(ask_gpt_func: Callable[[str, str], str]) -> None:
    global _ask_gpt
    _ask_gpt = ask_gpt_func


def answer(question: str) -> str:
    if not _ask_gpt:
        raise RuntimeError("Little Tree skill is not configured with an LLM caller")
    return LittleTreeAgent(_ask_gpt).answer(question)
