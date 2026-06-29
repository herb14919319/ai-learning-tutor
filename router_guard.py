from __future__ import annotations

import re
from dataclasses import dataclass


LEARNING = "learning"
LEARNING_GUIDANCE = "learning_guidance"
CASUAL_CHAT = "casual_chat"
TOOL_MISUSE = "tool_misuse"
UNKNOWN = "unknown"


BLOCKED_REDIRECT_MESSAGE = (
    "我主要是 AI Learning 助教，不能當一般聊天、圖片生成、角色扮演或 unrelated writing 工具使用。\n\n"
    "你可以改問 AI 學習相關問題，例如：\n"
    "1. Transformer 的 attention 是什麼？\n"
    "2. RAG 跟 fine-tuning 差在哪？\n"
    "3. 初學者該怎麼開始學機器學習？"
)

CLARIFICATION_MESSAGE = (
    "我想先確認一下：你想問的是 AI 或機器學習相關的學習問題嗎？\n\n"
    "可以像這樣問：\n"
    "1. 什麼是 Transformer？\n"
    "2. 初學者要怎麼學 LLM？\n"
    "3. RAG 適合解決什麼問題？"
)


@dataclass(frozen=True)
class GuardResult:
    intent: str
    allowed: bool
    response: str | None = None


LEARNING_TERMS = (
    "ai",
    "artificial intelligence",
    "machine learning",
    "ml",
    "deep learning",
    "dl",
    "neural network",
    "llm",
    "large language model",
    "rag",
    "fine-tuning",
    "finetuning",
    "transformer",
    "attention",
    "embedding",
    "token",
    "prompt",
    "agent",
    "mcp",
    "pytorch",
    "model training",
    "diffusion",
    "gan",
    "人工智慧",
    "機器學習",
    "深度學習",
    "神經網路",
    "生成式",
    "語言模型",
    "大型語言模型",
    "微調",
    "向量",
    "嵌入",
    "提示詞",
    "模型訓練",
)

GUIDANCE_TERMS = (
    "how should i learn",
    "how do i start",
    "where should i start",
    "learning path",
    "study plan",
    "beginner",
    "roadmap",
    "prerequisite",
    "recommend a course",
    "start learning",
    "怎麼學",
    "如何學",
    "從哪開始",
    "學習路線",
    "學習地圖",
    "讀書計畫",
    "初學",
    "新手",
    "入門",
    "先修",
)

CASUAL_CHAT_TERMS = (
    "hello",
    "hi",
    "hey",
    "good morning",
    "good night",
    "how are you",
    "what are you doing",
    "tell me a joke",
    "chat with me",
    "陪我聊天",
    "你好",
    "嗨",
    "早安",
    "晚安",
    "你在幹嘛",
    "講笑話",
    "聊天",
)

TOOL_MISUSE_TERMS = (
    "generate an image",
    "create an image",
    "make an image",
    "draw me",
    "make a picture",
    "roleplay as",
    "role play as",
    "act as my",
    "pretend to be",
    "be my girlfriend",
    "be my boyfriend",
    "girlfriend",
    "boyfriend",
    "fortune telling",
    "tell my fortune",
    "tarot",
    "astrology",
    "write an essay",
    "write my essay",
    "write a poem",
    "write a novel",
    "write an email",
    "cover letter",
    "resume",
    "生成圖片",
    "產生圖片",
    "畫一張",
    "幫我畫",
    "角色扮演",
    "扮演我",
    "假裝你是",
    "當我女友",
    "當我男友",
    "女朋友",
    "男朋友",
    "算命",
    "占卜",
    "塔羅",
    "星座",
    "寫作文",
    "寫情書",
    "寫小說",
    "寫履歷",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if term.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
                return True
            continue
        if term in text:
            return True
    return False


def classify_intent(user_text: str) -> str:
    text = (user_text or "").strip().lower()
    if not text:
        return UNKNOWN

    # Fail open for legacy mojibake / undecodable inputs instead of blocking a real student.
    if "\ufffd" in text:
        return LEARNING

    has_learning = _contains_any(text, LEARNING_TERMS)
    has_guidance = _contains_any(text, GUIDANCE_TERMS)

    if _contains_any(text, TOOL_MISUSE_TERMS):
        return TOOL_MISUSE
    if has_learning and has_guidance:
        return LEARNING_GUIDANCE
    if has_learning:
        return LEARNING
    if has_guidance:
        return LEARNING_GUIDANCE
    if _contains_any(text, CASUAL_CHAT_TERMS):
        return CASUAL_CHAT
    return UNKNOWN


def route_learning_boundary(user_text: str) -> GuardResult:
    intent = classify_intent(user_text)
    if intent in {LEARNING, LEARNING_GUIDANCE}:
        return GuardResult(intent=intent, allowed=True)
    if intent in {CASUAL_CHAT, TOOL_MISUSE}:
        return GuardResult(intent=intent, allowed=False, response=BLOCKED_REDIRECT_MESSAGE)
    return GuardResult(intent=UNKNOWN, allowed=False, response=CLARIFICATION_MESSAGE)
