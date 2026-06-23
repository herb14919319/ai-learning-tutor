from __future__ import annotations

import threading


MAX_CONTEXT_TURNS = 6

_conversation_context: dict[str, list[dict[str, str]]] = {}
_context_lock = threading.Lock()


def get_recent_context(user_id: str | None) -> list[dict[str, str]]:
    if not user_id:
        return []

    with _context_lock:
        return [message.copy() for message in _conversation_context.get(user_id, [])]


def add_message(user_id: str | None, role: str, content: str) -> None:
    if not user_id or role not in {"user", "assistant"}:
        return

    text = (content or "").strip()
    if not text:
        return

    with _context_lock:
        messages = _conversation_context.setdefault(user_id, [])
        messages.append({"role": role, "content": text})
        max_messages = MAX_CONTEXT_TURNS * 2
        if len(messages) > max_messages:
            del messages[:-max_messages]


def add_turn(user_id: str | None, user_message: str, assistant_message: str) -> None:
    add_message(user_id, "user", user_message)
    add_message(user_id, "assistant", assistant_message)


def clear_context(user_id: str | None = None) -> None:
    with _context_lock:
        if user_id is None:
            _conversation_context.clear()
        else:
            _conversation_context.pop(user_id, None)


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


def build_contextual_prompt(user_prompt: str, user_id: str | None = None) -> str:
    context_text = format_recent_context(get_recent_context(user_id))
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
