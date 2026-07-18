from __future__ import annotations

from typing import Any

from skills.contract import SkillContext, SkillRequest
from skills.metadata import SkillMetadata


class ModuleSkillAdapter:
    """Adapter for legacy skill modules that expose configure() and answer(question)."""

    def __init__(self, target: Any, metadata: SkillMetadata):
        self.target = target
        # Backward-compatible attribute used by a few integrations.
        self.module = target
        self.metadata = metadata

    def configure(self, context: SkillContext) -> None:
        configure = getattr(self.target, "configure", None)
        if callable(configure) and context.ask_gpt:
            configure(context.ask_gpt)

    def can_handle(self, request: SkillRequest) -> bool:
        if not self.metadata.enabled:
            return False
        text = request.text.lower()
        terms = self.metadata.domains + self.metadata.keywords
        return any(term.lower() in text for term in terms)

    def answer(self, request: SkillRequest | str, context: SkillContext | None = None) -> str:
        if context:
            self.configure(context)

        question = request.text if isinstance(request, SkillRequest) else request
        return self.target.answer(question)
