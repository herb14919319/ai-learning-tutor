"""Knowledge Packs: one contract over courses with different internal storage.

The pack registry is independent of chat routing; skill manifests remain the
only source of chat routability (see router_guard.manifest_scope_terms).
"""

from knowledge_packs.contract import (
    COURSE_INFO_FIELDS,
    GRADING_FIELDS,
    HIDDEN_QUESTION_FIELDS,
    QUESTION_FIELDS,
    ChapterFlashcards,
    ChapterQuestions,
    ContentSearch,
    KnowledgePack,
    SourceCatalog,
    SourceVerification,
)
from knowledge_packs.packs import AiApplicationPlannerPack, CybersecurityPack, NetZeroPlannerPack
from skills import ipas_ai_application_planner, ipas_cybersecurity, ipas_net_zero_planner

_PACKS: dict[str, KnowledgePack] = {
    pack.pack_id: pack
    for pack in (
        NetZeroPlannerPack(ipas_net_zero_planner),
        AiApplicationPlannerPack(ipas_ai_application_planner),
        CybersecurityPack(ipas_cybersecurity),
    )
}


def get_pack(pack_id: str) -> KnowledgePack:
    return _PACKS[pack_id]


def list_pack_ids() -> tuple[str, ...]:
    return tuple(_PACKS)


__all__ = [
    "COURSE_INFO_FIELDS",
    "GRADING_FIELDS",
    "HIDDEN_QUESTION_FIELDS",
    "QUESTION_FIELDS",
    "ChapterFlashcards",
    "ChapterQuestions",
    "ContentSearch",
    "KnowledgePack",
    "SourceCatalog",
    "SourceVerification",
    "get_pack",
    "list_pack_ids",
]
