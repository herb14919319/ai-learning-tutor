from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    display_name: str
    domains: tuple[str, ...]
    keywords: tuple[str, ...]
    description: str
    capabilities: tuple[str, ...] = ()
    entrypoint: str = ""
    priority: int = 0
    enabled: bool = True

    @property
    def domain(self) -> tuple[str, ...]:
        """Backward-compatible alias for the P2 metadata shape."""
        return self.domains
