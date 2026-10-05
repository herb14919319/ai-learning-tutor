"""Adapters exposing the existing iPAS skill packages through the Knowledge Pack contract.

Each adapter wraps the pack's module and calls it at request time, so the
module's own caching, validation, error types and review gates apply
unchanged (and patches on the module keep working). Adapters translate
signatures only; they never reshape payloads.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any


class _ModulePack:
    pack_id = ""

    def __init__(self, module: ModuleType):
        self._module = module

    @property
    def unavailable_error(self) -> type[Exception]:
        return self._module.DataUnavailableError

    def get_course_info(self) -> dict[str, Any]:
        return self._module.get_course_info()

    def get_chapters(self) -> list[dict[str, Any]]:
        return self._module.get_chapters()

    def get_chapter(self, chapter_id: str) -> dict[str, Any]:
        return self._module.get_chapter(chapter_id)

    def submit_answer(self, question_id: str, selected_answer: str) -> dict[str, Any]:
        return self._module.submit_answer(question_id, selected_answer)

    def get_sources(self) -> dict[str, Any]:
        return self._module.get_sources()


class NetZeroPlannerPack(_ModulePack):
    """Web-only course: eight Markdown chapters with image cards and generated questions."""

    pack_id = "ipas_net_zero_planner"

    def list_questions(self) -> list[dict[str, Any]]:
        return self._module.get_questions()

    def search(self, query: str) -> list[dict[str, Any]]:
        return self._module.search(query)


class AiApplicationPlannerPack(_ModulePack):
    """Seven-chapter course with a question bank per chapter."""

    pack_id = "ipas_ai_application_planner"

    def list_questions(self) -> list[dict[str, Any]]:
        return self._module.get_questions()

    def get_chapter_questions(self, chapter_id: str) -> list[dict[str, Any]]:
        return self._module.get_questions(chapter_id)


class CybersecurityPack(_ModulePack):
    """Source-verified slices with Learning Chunks, flashcards and a review ledger.

    Visibility follows the review gate: revision-required or rejected content and
    anything depending on it is absent from chapters, cards and questions.
    """

    pack_id = "ipas_cybersecurity"

    def list_questions(self) -> list[dict[str, Any]]:
        return [
            question
            for chapter in self._module.get_chapters()
            for question in self._module.get_questions(chapter["chapter_id"])
        ]

    def get_chapter_questions(self, chapter_id: str) -> list[dict[str, Any]]:
        return self._module.get_questions(chapter_id)

    def get_flashcards(self, chapter_id: str) -> list[dict[str, Any]]:
        return self._module.get_flashcards(chapter_id)

    def verify_sources(self) -> None:
        """Check the canonical PDF against source_manifest.json (raises review.ReviewError on mismatch)."""
        from skills.ipas_cybersecurity import review

        review.verify_source(review.PROCESSED, review.SOURCE)
