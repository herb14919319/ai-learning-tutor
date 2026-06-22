from __future__ import annotations

import re

from skills.registry import list_skills


def _matches_term(text: str, term: str) -> bool:
    normalized_term = term.lower()
    if normalized_term.isascii():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text))
    return normalized_term in text


def _matches_metadata(user_message: str, terms: tuple[str, ...]) -> bool:
    text = user_message.lower()
    return any(_matches_term(text, term) for term in terms)


def route(user_message: str) -> dict:
    for metadata in list_skills():
        if not metadata.enabled:
            continue
        if _matches_metadata(user_message, metadata.domains + metadata.keywords):
            return {"skill": metadata.name, "reason": "metadata_match"}
    return {"skill": "general", "reason": "default"}
