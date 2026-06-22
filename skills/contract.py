from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from skills.metadata import SkillMetadata


AskGpt = Callable[[str, str], str]


@dataclass(frozen=True)
class SkillRequest:
    text: str
    raw_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def question(self) -> str:
        return self.text


@dataclass(frozen=True)
class SkillContext:
    ask_gpt: AskGpt | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SkillContract(Protocol):
    metadata: SkillMetadata

    def can_handle(self, request: SkillRequest) -> bool:
        ...

    def answer(self, request: SkillRequest | str, context: SkillContext | None = None) -> str:
        ...
