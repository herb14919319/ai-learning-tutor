"""Learner-state boundary: the per-learner state the tutor keeps between messages.

Only two kinds of state exist today, and the interface covers exactly those:
short-term conversation context (the most recent turns) and the active skill.
Channel dedupe, rate limits, executors, locks and telemetry are not learner
state and live with their owners.

The default store is in memory and process-local, as before: it is lost on
restart and not shared between workers or instances.
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable


MAX_CONTEXT_TURNS = 6
MESSAGE_ROLES = frozenset({"user", "assistant"})


@runtime_checkable
class LearnerStateStore(Protocol):
    """State keyed by learner id. A missing or empty id is never stored and reads as empty."""

    def get_recent_messages(self, learner_id: str | None) -> list[dict[str, str]]:
        """Copies of the most recent messages, oldest first."""

    def append_message(self, learner_id: str | None, role: str, content: str) -> None:
        """Keep a user or assistant message (stripped; empty ignored), trimming to the most recent turns."""

    def get_active_skill(self, learner_id: str | None) -> str | None: ...

    def set_active_skill(self, learner_id: str | None, skill_name: str) -> None: ...

    def clear_active_skill(self, learner_id: str | None) -> None: ...

    def clear(self, learner_id: str | None = None) -> None:
        """Forget one learner's context and active skill, or every learner's when no id is given."""


class InMemoryLearnerStateStore:
    """Process-local learner state, identical to the pre-R6 module-level dictionaries."""

    def __init__(self, max_context_turns: int = MAX_CONTEXT_TURNS):
        self.max_context_turns = max_context_turns
        self._conversation_context: dict[str, list[dict[str, str]]] = {}
        self._active_skills: dict[str, str] = {}
        self._lock = threading.Lock()

    def get_recent_messages(self, learner_id: str | None) -> list[dict[str, str]]:
        if not learner_id:
            return []

        with self._lock:
            return [message.copy() for message in self._conversation_context.get(learner_id, [])]

    def append_message(self, learner_id: str | None, role: str, content: str) -> None:
        if not learner_id or role not in MESSAGE_ROLES:
            return

        text = (content or "").strip()
        if not text:
            return

        with self._lock:
            messages = self._conversation_context.setdefault(learner_id, [])
            messages.append({"role": role, "content": text})
            max_messages = self.max_context_turns * 2
            if len(messages) > max_messages:
                del messages[:-max_messages]

    def get_active_skill(self, learner_id: str | None) -> str | None:
        if not learner_id:
            return None

        with self._lock:
            return self._active_skills.get(learner_id)

    def set_active_skill(self, learner_id: str | None, skill_name: str) -> None:
        if not learner_id or not skill_name:
            return

        with self._lock:
            self._active_skills[learner_id] = skill_name

    def clear_active_skill(self, learner_id: str | None) -> None:
        if not learner_id:
            return

        with self._lock:
            self._active_skills.pop(learner_id, None)

    def clear(self, learner_id: str | None = None) -> None:
        with self._lock:
            if learner_id is None:
                self._conversation_context.clear()
                self._active_skills.clear()
            else:
                self._conversation_context.pop(learner_id, None)
                self._active_skills.pop(learner_id, None)


_default_store: LearnerStateStore = InMemoryLearnerStateStore()


def get_learner_state_store() -> LearnerStateStore:
    """The process-wide store used by the tutor runtime."""
    return _default_store
