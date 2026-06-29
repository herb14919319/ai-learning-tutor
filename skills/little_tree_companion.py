from __future__ import annotations

import logging
from typing import Callable


logger = logging.getLogger(__name__)

LITTLE_TREE_SKILL_NAME = "little_tree_companion"
WELCOME_MESSAGE = (
    "🌱 歡迎來到小樹 AI 陪伴模式！\n"
    "我是你的 AI 學習夥伴。\n"
    "你可以問我 AI、故事、功課、英文、數學，或請我陪你一起想點子。\n"
    "想回到一般 AI Tutor，輸入 `/離開` 就可以囉！"
)
EXIT_MESSAGE = "已回到一般 AI Tutor（李教授）模式。你可以繼續問 AI、機器學習或生成式 AI 的問題。"

_ask_gpt: Callable[[str, str], str] | None = None


def configure(ask_gpt_func: Callable[[str, str], str]) -> None:
    global _ask_gpt
    _ask_gpt = ask_gpt_func


def answer(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "我在這裡陪你慢慢想。你今天想問哪一題呢？"

    if not _ask_gpt:
        raise RuntimeError("Little Tree skill is not configured with an LLM caller")

    try:
        return _ask_gpt(build_system_prompt(), f"孩子的問題：{question}")
    except Exception:
        logger.exception("Little Tree companion answer failed")
        raise


def build_system_prompt() -> str:
    return """你是「小樹 AI 陪伴模式」的 AI 學習夥伴。
服務對象是透過小樹傳愛協會 / 善愛嘉年華，以及賽珍珠基金會學習支持活動接觸到的小學生。

請用繁體中文回答。
對象約 7 到 12 歲。
語氣像溫柔、有耐心、會鼓勵人的哥哥姊姊或陪讀老師。
句子短一點。
多用生活例子。
不要責備孩子不知道。
稱讚孩子的努力、好奇和願意嘗試。
多用提問引導，不要一次給太長的答案。
多數回覆盡量少於 180 個中文字。
適合時，用一個簡單問題收尾。

除非孩子主動問，避免使用 Transformer、Token、Attention、Embedding、RAG 等難詞。
如果必須提到，請用很簡單的比喻說明。

安全規則：
不要提供危險、暴力、性、自傷、醫療、法律或金錢投資建議。
遇到身體不舒服、受傷、被欺負、害怕、自傷想法、家庭危險或其他敏感事情時，溫柔回應，並鼓勵孩子立刻找可信任的大人，例如家人、老師、社工或輔導老師。
"""
