from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from importlib import import_module

from skills.adapters import ModuleSkillAdapter
from skills.contract import AskGpt, SkillContext, SkillRequest
from skills.metadata import SkillMetadata


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillManifest:
    name: str
    display_name: str
    description: str
    domains: tuple[str, ...]
    keywords: tuple[str, ...]
    capabilities: tuple[str, ...]
    entrypoint: str
    priority: int = 0
    enabled: bool = True
    status: str = "active"
    skill_type: str = "runtime"
    aliases: tuple[str, ...] = ()
    content_root: str | None = None
    chapter_index: str | None = None
    source: str = ""

    def to_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name=self.name,
            display_name=self.display_name,
            domains=self.domains,
            keywords=self.keywords,
            description=self.description,
            capabilities=self.capabilities,
            entrypoint=self.entrypoint,
            priority=self.priority,
            enabled=self.enabled,
        )


def _matches_term(text: str, term: str) -> bool:
    normalized_term = term.lower()
    if normalized_term.isascii():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text))
    return normalized_term in text


def metadata_matches(request: SkillRequest, metadata: SkillMetadata) -> bool:
    text = request.text.lower()
    return any(_matches_term(text, term) for term in metadata.domains + metadata.keywords)


class SkillCatalog:
    def __init__(self, manifests: tuple[SkillManifest, ...]):
        self._manifests = {manifest.name: manifest for manifest in manifests}

    def list_metadata(self, *, include_disabled: bool = True) -> list[SkillMetadata]:
        metadata = [
            manifest.to_metadata()
            for manifest in self._manifests.values()
            if include_disabled or manifest.enabled
        ]
        return sorted(metadata, key=lambda item: item.priority, reverse=True)

    def get_manifest(self, skill_name: str) -> SkillManifest | None:
        return self._manifests.get(skill_name)

    def get_metadata(self, skill_name: str) -> SkillMetadata | None:
        manifest = self.get_manifest(skill_name)
        if not manifest:
            return None
        return manifest.to_metadata()


class SkillRuntime:
    def __init__(
        self,
        catalog: SkillCatalog,
        loaded_skills: dict[str, ModuleSkillAdapter] | None = None,
    ):
        self.catalog = catalog
        self.context = SkillContext()
        self._skills: dict[str, ModuleSkillAdapter] = dict(loaded_skills or {})

    def configure(self, ask_gpt: AskGpt) -> None:
        self.context = SkillContext(ask_gpt=ask_gpt)
        for skill in self._skills.values():
            skill.configure(self.context)

    def normalize_request(self, user_message: str) -> SkillRequest:
        text = (user_message or "").strip()
        return SkillRequest(text=text, raw_text=user_message)

    def route(self, request: SkillRequest) -> dict:
        for metadata in self.catalog.list_metadata(include_disabled=False):
            if metadata_matches(request, metadata):
                return {"skill": metadata.name, "reason": "metadata_match"}
        return {"skill": "general", "reason": "default"}

    def get_skill(self, skill_name: str) -> ModuleSkillAdapter | None:
        manifest = self.catalog.get_manifest(skill_name)
        if not manifest:
            return None
        if not manifest.enabled:
            logger.info("Skill is disabled: %s", skill_name)
            return None
        if skill_name not in self._skills:
            module_name, separator, attribute = manifest.entrypoint.partition(":")
            target = import_module(module_name)
            if separator:
                factory = getattr(target, attribute)
                target = factory()
            if not callable(getattr(target, "answer", None)):
                raise TypeError(f"Skill entrypoint does not provide answer(): {skill_name}")
            self._skills[skill_name] = ModuleSkillAdapter(target, manifest.to_metadata())
            self._skills[skill_name].configure(self.context)
        return self._skills[skill_name]

    def invoke(self, skill_name: str, request: SkillRequest) -> str | None:
        skill = self.get_skill(skill_name)
        if not skill:
            return None
        return skill.answer(request, self.context)
