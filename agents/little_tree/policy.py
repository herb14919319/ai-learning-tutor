from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agents.little_tree.intent import LittleTreeIntent


class PolicyAction(StrEnum):
    ALLOW = "allow"
    GUIDE = "guide_instead_of_answering"
    REFUSE = "refuse"


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    reason: str
    prompt_instruction: str


UNSAFE_TERMS = (
    "suicide",
    "self harm",
    "kill",
    "weapon",
    "bomb",
    "hack",
    "steal password",
    "illegal",
    "毒品",
    "自殺",
    "自殘",
    "殺人",
    "武器",
    "炸彈",
    "駭入",
    "偷密碼",
    "違法",
)


def _has_unsafe_request(user_text: str) -> bool:
    text = (user_text or "").strip().lower()
    return any(term in text for term in UNSAFE_TERMS)


def decide_policy(user_text: str, intent: LittleTreeIntent) -> PolicyDecision:
    if _has_unsafe_request(user_text):
        return PolicyDecision(
            action=PolicyAction.REFUSE,
            reason="unsafe_or_illegal_request",
            prompt_instruction="拒絕 unsafe、illegal 或 harmful content；保持溫和，並引導到安全的大人或正當資源。",
        )

    if intent == LittleTreeIntent.HOMEWORK_GUIDANCE:
        return PolicyDecision(
            action=PolicyAction.GUIDE,
            reason="homework_exam_or_assignment",
            prompt_instruction="這是作業、考題或任務請求；不要直接完成答案，要用提示、反問、拆步驟與檢查問題引導。",
        )

    return PolicyDecision(
        action=PolicyAction.ALLOW,
        reason="within_little_tree_scope",
        prompt_instruction="允許回答；聚焦 AI learning、prompting、critical thinking、parent guidance、volunteer guidance 或 teacher guidance。",
    )
