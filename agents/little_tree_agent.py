from __future__ import annotations

import logging
from typing import Callable

from memory.conversation_context import add_turn
from memory.conversation_context import build_contextual_prompt


logger = logging.getLogger(__name__)

LITTLE_TREE_SKILL_NAME = "little_tree_companion"
LITTLE_TREE_COMMAND = "/小樹"
LITTLE_TREE_EXIT_COMMANDS = {"/離開", "/李教授"}

WELCOME_MESSAGE = (
    "🌱 歡迎來到小樹 AI 陪伴模式！\n"
    "我是小樹 AI 陪伴夥伴。\n"
    "我希望陪伴孩子與家長，一起認識 AI、探索 AI，學會安全又有智慧地使用 AI。\n"
    "這裡不是幫你把功課寫完的地方，而是陪你一起思考、一起成長。\n"
    "如果你是家長，也歡迎和我一起探索如何陪伴孩子進入 AI 的世界。\n"
    "想回到一般 AI Tutor，輸入 `/離開` 就可以囉！"
)
EXIT_MESSAGE = "已回到一般 AI Tutor（李教授）模式。你可以繼續問 AI、機器學習或生成式 AI 的問題。"
EMPTY_MESSAGE = "我在這裡陪你慢慢認識 AI。你想先聊聊 AI 可以做什麼，還是 AI 可能會犯錯呢？"


class LittleTreeAgent:
    """AI literacy companion for Little Tree mode."""

    def __init__(self, ask_gpt: Callable[[str, str], str]):
        self._ask_gpt = ask_gpt

    def can_handle(self, user_message: str) -> bool:
        text = (user_message or "").strip().lower()
        if text == LITTLE_TREE_COMMAND or text in LITTLE_TREE_EXIT_COMMANDS:
            return True

        markers = (
            "ai素養",
            "ai 素養",
            "親子",
            "共學",
            "孩子",
            "兒童",
            "小朋友",
            "家長",
            "志工",
            "老師",
            "作業",
            "功課",
            "怎麼陪",
            "如何陪",
            "ai literacy",
            "parent",
            "child",
            "homework",
        )
        return any(marker in text for marker in markers)

    def answer(self, user_message: str, *, user_id: str | None = None) -> str:
        question = (user_message or "").strip()
        if not question:
            return EMPTY_MESSAGE

        try:
            reply = self._ask_gpt(
                build_system_prompt(),
                build_user_prompt(question, user_id=user_id),
            )
        except Exception:
            logger.exception("LittleTreeAgent answer failed")
            raise

        add_turn(user_id, user_message, reply)
        return reply


def build_user_prompt(question: str, *, user_id: str | None = None) -> str:
    return build_contextual_prompt(f"使用者的問題：{question}", user_id)


def build_system_prompt() -> str:
    return """你是「小樹 AI 陪伴模式」的 AI 素養陪伴 Agent。
你的使命受到小樹傳愛協會精神啟發：喚醒每個人心中愛與被愛的能力。

定位與邊界：
- 你是 AI 素養、親子共學、兒童引導、家長陪伴、志工與老師支持的陪伴者。
- 你不是作業代寫工具，也不是直接給標準答案的解題機器。
- 遇到作業、考題、學習單、作文、報告或計算題時，不直接給答案；用提示、反問、拆解步驟、例子和檢查問題，引導孩子自己想出下一步。
- 可以協助家長、志工、老師設計陪伴方式、提問方式、討論活動與安全使用 AI 的規則。
- 可以用孩子聽得懂的語言解釋 AI 概念，例如 AI 會怎麼學、為什麼會犯錯、資料偏誤、隱私、網路安全、生成式 AI、提示語、查證與負責任使用。

語氣：
- 使用繁體中文。
- 溫和、鼓勵、親子共學，不責備、不恐嚇。
- 回答要短而清楚，通常 180 字以內；必要時用條列。
- 先接住情緒或需求，再提出一兩個可以立刻做的小步驟。

作業引導規則：
- 如果使用者要求「直接幫我寫」「給答案」「整篇作文」「完整解答」，先溫和說明你不能代寫或直接給答案。
- 接著提供思考框架，例如：「我們先找題目問什麼」「你已經知道哪些線索」「先試第一步，我幫你檢查」。
- 可以示範一小段方法，但不要完成整份作業。

AI 素養重點：
- 鼓勵查證，不把 AI 回答當成唯一真相。
- 提醒不要輸入個資、家庭地址、帳號密碼、同學隱私。
- 幫孩子理解 AI 是工具，不是替代思考或替代關係的人。
- 鼓勵大人陪孩子一起問、一起比較、一起討論。
"""
