from __future__ import annotations

from typing import Callable

from skills.metadata import SkillMetadata
from skills.runtime import SkillCatalog, SkillManifest, SkillRuntime


SKILL_MANIFESTS = (
    SkillManifest(
        name="hungyi_lee",
        display_name="Hung-yi Lee AI Tutor",
        domains=("AI", "ML", "LLM", "deep learning", "generative AI"),
        keywords=(
            "Transformer",
            "RAG",
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
    return DEFAULT_CATALOG.list_metadata()


def get_skill_metadata(skill_name: str) -> SkillMetadata | None:
    return DEFAULT_CATALOG.get_metadata(skill_name)


def get_runtime() -> SkillRuntime:
    return DEFAULT_RUNTIME
