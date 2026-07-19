from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SKILL_ID = "little_tree"
ROOT = Path(__file__).resolve().parent
DEFAULT_CONTENT_DIR = ROOT / "content"
CATEGORIES_FILE = "categories.json"
CATEGORY_FIELDS = ("id", "title", "description", "icon", "route")
PARENTING_SCENARIOS_FILE = Path("parenting") / "scenarios.json"
SCENARIO_FIELDS = ("id", "title", "description", "prompt")
PARENTING_SCENARIO_COUNT = 3


class DataUnavailableError(RuntimeError):
    """Raised when required local Little Tree content cannot be read."""


class ContentFormatError(DataUnavailableError):
    """Raised when local Little Tree content does not match its fixed schema."""


class LittleTreeSkill:
    skill_id = SKILL_ID

    def __init__(self, content_dir: Path | None = None):
        self.content_dir = Path(content_dir or DEFAULT_CONTENT_DIR)

    def get_categories(self) -> list[dict[str, str]]:
        path = self.content_dir / CATEGORIES_FILE
        if not path.is_file():
            raise DataUnavailableError("Little Tree categories are unavailable.")

        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DataUnavailableError("Little Tree categories could not be read.") from exc

        if not isinstance(payload, list):
            raise ContentFormatError("Little Tree categories must be a JSON array.")

        categories: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        seen_routes: set[str] = set()
        for item in payload:
            if not isinstance(item, dict) or set(item) != set(CATEGORY_FIELDS):
                raise ContentFormatError("A Little Tree category has an invalid schema.")
            if any(not isinstance(item[field], str) or not item[field].strip() for field in CATEGORY_FIELDS):
                raise ContentFormatError("A Little Tree category contains an empty field.")

            category = {field: item[field].strip() for field in CATEGORY_FIELDS}
            if category["id"] in seen_ids or category["route"] in seen_routes:
                raise ContentFormatError("Little Tree category ids and routes must be unique.")
            if not category["route"].startswith("/little-tree/"):
                raise ContentFormatError("A Little Tree category route is invalid.")

            seen_ids.add(category["id"])
            seen_routes.add(category["route"])
            categories.append(category)

        return categories

    def get_parenting_scenarios(self) -> list[dict[str, str]]:
        path = self.content_dir / PARENTING_SCENARIOS_FILE
        if not path.is_file():
            raise DataUnavailableError("Little Tree parenting scenarios are unavailable.")

        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DataUnavailableError(
                "Little Tree parenting scenarios could not be read."
            ) from exc

        if not isinstance(payload, list):
            raise ContentFormatError(
                "Little Tree parenting scenarios must be a JSON array."
            )
        if len(payload) != PARENTING_SCENARIO_COUNT:
            raise ContentFormatError(
                f"Little Tree parenting scenarios must contain {PARENTING_SCENARIO_COUNT} items."
            )

        scenarios: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in payload:
            if not isinstance(item, dict) or set(item) != set(SCENARIO_FIELDS):
                raise ContentFormatError(
                    "A Little Tree parenting scenario has an invalid schema."
                )
            if any(
                not isinstance(item[field], str) or not item[field].strip()
                for field in SCENARIO_FIELDS
            ):
                raise ContentFormatError(
                    "A Little Tree parenting scenario contains an empty field."
                )

            scenario = {field: item[field].strip() for field in SCENARIO_FIELDS}
            if scenario["id"] in seen_ids:
                raise ContentFormatError(
                    "Little Tree parenting scenario ids must be unique."
                )
            seen_ids.add(scenario["id"])
            scenarios.append(scenario)

        return scenarios


_default_skill = LittleTreeSkill()


def get_categories() -> list[dict[str, str]]:
    return _default_skill.get_categories()


def get_parenting_scenarios() -> list[dict[str, str]]:
    return _default_skill.get_parenting_scenarios()
