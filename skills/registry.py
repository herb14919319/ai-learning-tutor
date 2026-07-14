from __future__ import annotations

from typing import Callable

from skills.metadata import SkillMetadata
from skills.runtime import SkillCatalog, SkillManifest, SkillRuntime


SKILL_MANIFESTS = (
    SkillManifest(
        name="little_tree_companion",
        display_name="Little Tree Companion",
        domains=(),
        keywords=("/小樹",),
        description=(
            "Gentle Traditional Chinese AI learning companion for elementary-school "
            "children in Little Tree learning support mode."
        ),
        capabilities=("child_friendly_learning_companion",),
        entrypoint="skills.little_tree_companion",
        priority=200,
        enabled=False,
    ),
    SkillManifest(
        name="hungyi_lee",
        display_name="Hung-yi Lee AI Tutor",
        domains=("AI", "ML", "LLM", "deep learning", "generative AI"),
        keywords=(
            "Transformer",
            "MCP",
            "RAG",
            "Agent",
            "AI Agent",
            "Tool Calling",
            "Function Calling",
            "Prompt",
            "Embedding",
            "Vector DB",
            "Vector Database",
            "fine-tune",
            "attention",
            "machine learning",
            "深度學習",
            "機器學習",
            "生成式AI",
        ),
        description=(
            "AI, machine learning, deep learning, LLM, and generative AI tutoring "
            "based on Hung-yi Lee teaching materials."
        ),
        capabilities=("answer_ai_learning_question", "grounded_tutoring"),
        entrypoint="skills.hungyi_lee_skill",
        priority=100,
        enabled=True,
    ),
)

DEFAULT_CATALOG = SkillCatalog(SKILL_MANIFESTS)
DEFAULT_RUNTIME = SkillRuntime(DEFAULT_CATALOG)


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
