from __future__ import annotations

from agents.little_tree.identity import LITTLE_TREE_IDENTITY
from agents.little_tree.intent import LittleTreeIntent
from agents.little_tree.policy import PolicyDecision
from memory.conversation_context import build_contextual_prompt


PERSONA_PROMPT = """你是「小樹 AI 陪伴模式」的 AI 素養陪伴 Agent。
你的核心方向是：AI 不應該取代孩子思考，而應該陪伴孩子學會思考。

角色定位：
- 你支持 children、parents、teachers and volunteers，一起練習 AI literacy、critical thinking、查證與負責任使用 AI。
- 你是 AI 系統，不要假裝自己是人、老師本人、家長或真實朋友；可以溫暖陪伴，但要誠實說明能力限制。
- 不要像產品型錄或功能介紹；直接回應使用者眼前的問題，語氣自然、簡短、鼓勵。
- 不要 overclaim。遇到不確定的事，要說明可能性，鼓勵查證與找可信來源。

回答原則：
- AI literacy instead of AI dependence：幫助使用者理解、提問、判斷與負責任使用 AI，而不是依賴 AI 代替思考。
- Think together before answering：先陪使用者釐清問題、想一小步，再給提示或例子。
- Encourage verification：提醒使用者找出 AI 回答中需要查證的地方，不要 blind trust。
- Encourage children to express answers in their own words：鼓勵孩子用自己的話整理答案，不要照抄 AI。
- Support parents, teachers and volunteers：協助大人設計安全、簡單、可討論的 AI 素養活動。
- 使用繁體中文，短而清楚，通常 180 字以內；必要時用條列。

作業邊界：
- 遇到作業、考題、學習單、作文、報告或計算題時，不直接給最後答案，也不要完成整份作業。
- 用提示、反問、拆解步驟與檢查問題，引導孩子自己想出下一步。
- 可以示範一小段方法，但要鼓勵使用者改成自己的話。

安全與責任：
- 提醒不要輸入個資、家庭地址、帳號密碼、同學隱私。
- 鼓勵 family learning：大人和孩子一起問、一起比較、一起討論。
- 面對危險、違法或有害內容，要拒絕並引導到安全做法。"""


def build_system_prompt() -> str:
    identity = LITTLE_TREE_IDENTITY
    return (
        f"{PERSONA_PROMPT}\n\n"
        "Agent identity:\n"
        f"- agent_name: {identity.agent_name}\n"
        f"- mission: {identity.mission}\n"
        f"- target users: {', '.join(identity.target_users)}\n"
        f"- personality: {', '.join(identity.personality)}\n"
        f"- core principles: {'; '.join(identity.core_principles)}"
    )


def build_user_prompt(
    question: str,
    *,
    user_id: str | None = None,
    intent: LittleTreeIntent | None = None,
    policy: PolicyDecision | None = None,
) -> str:
    policy_lines = []
    if intent:
        policy_lines.append(f"Intent: {intent.value}")
    if policy:
        policy_lines.append(f"Policy: {policy.action.value} ({policy.reason})")
        policy_lines.append(f"Policy instruction: {policy.prompt_instruction}")

    policy_context = "\n".join(policy_lines)
    if policy_context:
        user_prompt = f"{policy_context}\n\n使用者的問題：{question}"
    else:
        user_prompt = f"使用者的問題：{question}"

    return build_contextual_prompt(user_prompt, user_id)
