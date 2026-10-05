from __future__ import annotations

from memory.learner_state import MAX_CONTEXT_TURNS, LearnerStateStore, get_learner_state_store


# Compatibility API over the learner-state store (memory/learner_state.py). This
# module holds no state of its own; it also formats the short-term context prompt.
__all__ = [
    "MAX_CONTEXT_TURNS",
    "add_message",
    "add_turn",
    "build_contextual_prompt",
    "build_user_prompt",
    "clear_active_skill",
    "clear_context",
    "format_recent_context",
    "get_active_skill",
    "get_recent_context",
    "set_active_skill",
]


def get_recent_context(user_id: str | None) -> list[dict[str, str]]:
    return get_learner_state_store().get_recent_messages(user_id)


def add_message(user_id: str | None, role: str, content: str) -> None:
    get_learner_state_store().append_message(user_id, role, content)


def add_turn(
    user_id: str | None,
    user_message: str,
    assistant_message: str,
    store: LearnerStateStore | None = None,
) -> None:
    store = store or get_learner_state_store()
    store.append_message(user_id, "user", user_message)
    store.append_message(user_id, "assistant", assistant_message)


def clear_context(user_id: str | None = None) -> None:
    get_learner_state_store().clear(user_id)


def get_active_skill(user_id: str | None) -> str | None:
    return get_learner_state_store().get_active_skill(user_id)


def set_active_skill(user_id: str | None, skill_name: str) -> None:
    get_learner_state_store().set_active_skill(user_id, skill_name)


def clear_active_skill(user_id: str | None) -> None:
    get_learner_state_store().clear_active_skill(user_id)


def format_recent_context(messages: list[dict[str, str]]) -> str:
    if not messages:
        return ""

    lines = ["最近對話："]
    for message in messages:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")

    return "\n".join(lines).strip()


def build_contextual_prompt(
    user_prompt: str,
    user_id: str | None = None,
    store: LearnerStateStore | None = None,
) -> str:
    context_text = format_recent_context((store or get_learner_state_store()).get_recent_messages(user_id))
    if not context_text:
        return user_prompt

    return (
        f"{context_text}\n\n"
        "請把最近對話只當作短期上下文，用來理解學生是否在承接上一輪。"
        "不要把它當成永久記憶，也不要因此改變工具或 Skill 的選擇。\n\n"
        f"{user_prompt}"
    )


def build_user_prompt(user_message: str, user_id: str | None = None) -> str:
    return build_contextual_prompt(f"學生問題：{user_message}", user_id)
