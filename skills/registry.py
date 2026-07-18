from __future__ import annotations

from pathlib import Path
from typing import Callable

from skills.discovery import DiscoveryResult, SkillDiagnostic, discover_skills
from skills.metadata import SkillMetadata
from skills.runtime import SkillCatalog, SkillManifest, SkillRuntime


SKILLS_ROOT = Path(__file__).resolve().parent
DISCOVERY_RESULT: DiscoveryResult = discover_skills(SKILLS_ROOT)

# Backward-compatible projection. The source of truth is now validated
# skill.json files rather than a Python tuple maintained in this module.
SKILL_MANIFESTS: tuple[SkillManifest, ...] = DISCOVERY_RESULT.manifests
DEFAULT_CATALOG = SkillCatalog(SKILL_MANIFESTS)
DEFAULT_RUNTIME = SkillRuntime(DEFAULT_CATALOG, DISCOVERY_RESULT.loaded_skills)


def configure(ask_gpt_func: Callable[[str, str], str]) -> None:
    DEFAULT_RUNTIME.configure(ask_gpt_func)


def get_skill(skill_name: str):
    return DEFAULT_RUNTIME.get_skill(skill_name)


def list_skills() -> list[SkillMetadata]:
    return DEFAULT_CATALOG.list_metadata(include_disabled=False)


def get_skill_metadata(skill_name: str) -> SkillMetadata | None:
    return DEFAULT_CATALOG.get_metadata(skill_name)


def get_runtime() -> SkillRuntime:
    return DEFAULT_RUNTIME


def list_skill_manifests() -> tuple[SkillManifest, ...]:
    return SKILL_MANIFESTS


def list_unavailable_skills() -> dict[str, str]:
    return dict(DISCOVERY_RESULT.unavailable)


def list_skill_diagnostics() -> tuple[SkillDiagnostic, ...]:
    return DISCOVERY_RESULT.diagnostics
