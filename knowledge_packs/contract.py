"""Knowledge Pack contract.

A Knowledge Pack exposes a course's content through one interface without
sharing internal storage. Being a pack says nothing about chat: whether a
pack is chat-routable is decided only by its skill manifest (skills/*/skill.json).

Required operations are those every existing pack already supports. Payloads
are the pack's own dictionaries, passed through unchanged; the contract only
guarantees the common fields listed below. Optional capabilities are separate
protocols that a pack implements only when it really has the feature; detect
them with isinstance().
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


# Fields every pack's get_course_info() returns.
COURSE_INFO_FIELDS = ("skill_id", "title", "chapter_count", "first_chapter_id")
# Fields every pack's submit_answer() returns; packs may add more (citations, review status, ...).
GRADING_FIELDS = ("question_id", "selected_answer", "correct", "correct_answer", "explanation")
# Fields every public question carries; answers and explanations are never included.
QUESTION_FIELDS = ("question_id", "options")
HIDDEN_QUESTION_FIELDS = ("correct_answer", "explanation")


@runtime_checkable
class KnowledgePack(Protocol):
    pack_id: str

    @property
    def unavailable_error(self) -> type[Exception]:
        """The pack's own error class for missing or invalid course data."""

    def get_course_info(self) -> dict[str, Any]: ...

    def get_chapters(self) -> list[dict[str, Any]]:
        """Chapters in course order; each has a chapter_id."""

    def get_chapter(self, chapter_id: str) -> dict[str, Any]:
        """One chapter's detail; raises ValueError for an unknown chapter."""

    def list_questions(self) -> list[dict[str, Any]]:
        """Every question a learner can currently see, in course order, without answers."""

    def submit_answer(self, question_id: str, selected_answer: str) -> dict[str, Any]:
        """Grade one answer; raises ValueError for an unknown or unavailable question."""


@runtime_checkable
class ChapterQuestions(Protocol):
    def get_chapter_questions(self, chapter_id: str) -> list[dict[str, Any]]: ...


@runtime_checkable
class SourceCatalog(Protocol):
    def get_sources(self) -> dict[str, Any]: ...


@runtime_checkable
class ChapterFlashcards(Protocol):
    def get_flashcards(self, chapter_id: str) -> list[dict[str, Any]]: ...


@runtime_checkable
class ContentSearch(Protocol):
    def search(self, query: str) -> list[dict[str, Any]]: ...


@runtime_checkable
class SourceVerification(Protocol):
    def verify_sources(self) -> None:
        """Raise if the canonical sources no longer match their recorded hashes."""
