from __future__ import annotations

import re
from enum import StrEnum


class LittleTreeIntent(StrEnum):
    LEARNING_QUESTION = "learning_question"
    PARENT_SUPPORT = "parent_support"
    TEACHER_SUPPORT = "teacher_support"
    VOLUNTEER_SUPPORT = "volunteer_support"
    HOMEWORK_GUIDANCE = "homework_guidance"
    GENERAL_CHAT = "general_chat"
    UNKNOWN = "unknown"


LEARNING_TERMS = (
    "ai",
    "artificial intelligence",
    "prompt",
    "prompting",
    "chatgpt",
    "llm",
    "machine learning",
    "generative ai",
    "ai literacy",
    "素養",
    "提示",
    "提示語",
    "生成式",
    "人工智慧",
    "機器學習",
    "查證",
    "驗證",
    "隱私",
    "偏誤",
)

PARENT_TERMS = ("parent", "parents", "family", "家長", "爸媽", "父母", "親子", "家庭")
TEACHER_TERMS = ("teacher", "teachers", "classroom", "lesson", "老師", "教師", "課堂", "教案")
VOLUNTEER_TERMS = ("volunteer", "volunteers", "mentor", "志工", "陪伴者", "輔導")
HOMEWORK_TERMS = (
    "homework",
    "assignment",
    "exam",
    "quiz",
    "worksheet",
    "essay",
    "report",
    "answer this",
    "solve this",
    "write my",
    "作業",
    "功課",
    "考題",
    "考卷",
    "學習單",
    "作文",
    "報告",
    "幫我寫",
    "直接給答案",
    "完整解答",
)
CHAT_TERMS = ("hi", "hello", "hey", "你好", "嗨", "哈囉", "謝謝")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if term.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
                return True
            continue
        if term in text:
            return True
    return False


def classify_intent(user_text: str) -> LittleTreeIntent:
    text = (user_text or "").strip().lower()
    if not text:
        return LittleTreeIntent.UNKNOWN

    if _contains_any(text, HOMEWORK_TERMS):
        return LittleTreeIntent.HOMEWORK_GUIDANCE
    if _contains_any(text, PARENT_TERMS):
        return LittleTreeIntent.PARENT_SUPPORT
    if _contains_any(text, TEACHER_TERMS):
        return LittleTreeIntent.TEACHER_SUPPORT
    if _contains_any(text, VOLUNTEER_TERMS):
        return LittleTreeIntent.VOLUNTEER_SUPPORT
    if _contains_any(text, LEARNING_TERMS):
        return LittleTreeIntent.LEARNING_QUESTION
    if _contains_any(text, CHAT_TERMS):
        return LittleTreeIntent.GENERAL_CHAT
    return LittleTreeIntent.UNKNOWN
