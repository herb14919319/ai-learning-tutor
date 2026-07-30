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
SCENARIO_OPTIONAL_FIELDS = (
    "action_label",
    "editable",
    "questions",
    "demo_image",
    "demo_image_alt",
    "demo_title",
    "demo_message",
    "form_fields",
    "update_button_text",
    "update_success_message",
    "icon",
    "card_class",
)
QUESTION_FIELDS = ("label", "examples")
FORM_FIELD_STRING_FIELDS = ("id", "label", "examples", "placeholder", "token")
FORM_FIELD_FIELDS = (*FORM_FIELD_STRING_FIELDS, "inspirations")
DEMO_FIELDS = ("demo_image", "demo_image_alt", "demo_title", "demo_message")
UPDATE_FIELDS = ("update_button_text", "update_success_message")
VISUAL_FIELDS = ("icon", "card_class")
PARENTING_SCENARIO_COUNT = 4


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

    def get_parenting_scenarios(self) -> list[dict[str, Any]]:
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

        scenarios: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in payload:
            if (
                not isinstance(item, dict)
                or not set(SCENARIO_FIELDS).issubset(item)
                or not set(item).issubset((*SCENARIO_FIELDS, *SCENARIO_OPTIONAL_FIELDS))
            ):
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

            if "action_label" in item and (
                not isinstance(item["action_label"], str)
                or not item["action_label"].strip()
            ):
                raise ContentFormatError(
                    "A Little Tree parenting scenario action label is invalid."
                )
            if "editable" in item and not isinstance(item["editable"], bool):
                raise ContentFormatError(
                    "A Little Tree parenting scenario editable flag is invalid."
                )
            if "questions" in item and (
                not isinstance(item["questions"], list)
                or not item["questions"]
                or any(
                    not isinstance(question, dict)
                    or set(question) != set(QUESTION_FIELDS)
                    or any(
                        not isinstance(question[field], str)
                        or not question[field].strip()
                        for field in QUESTION_FIELDS
                    )
                    for question in item["questions"]
                )
            ):
                raise ContentFormatError(
                    "A Little Tree parenting scenario question guide is invalid."
                )
            if any(field in item for field in DEMO_FIELDS) and (
                not all(field in item for field in DEMO_FIELDS)
                or any(
                    not isinstance(item[field], str) or not item[field].strip()
                    for field in DEMO_FIELDS
                )
            ):
                raise ContentFormatError(
                    "A Little Tree parenting scenario demo image is invalid."
                )
            if "form_fields" in item and (
                not isinstance(item["form_fields"], list)
                or not item["form_fields"]
                or any(
                    not isinstance(form_field, dict)
                    or set(form_field) != set(FORM_FIELD_FIELDS)
                    or any(
                        not isinstance(form_field[field], str)
                        or not form_field[field].strip()
                        for field in FORM_FIELD_STRING_FIELDS
                    )
                    or not isinstance(form_field["inspirations"], list)
                    or not form_field["inspirations"]
                    or any(
                        not isinstance(inspiration, str)
                        or not inspiration.strip()
                        for inspiration in form_field["inspirations"]
                    )
                    for form_field in item["form_fields"]
                )
                or len(
                    {
                        form_field["id"].strip()
                        for form_field in item["form_fields"]
                    }
                )
                != len(item["form_fields"])
                or len(
                    {
                        form_field["token"].strip()
                        for form_field in item["form_fields"]
                    }
                )
                != len(item["form_fields"])
            ):
                raise ContentFormatError(
                    "A Little Tree parenting scenario form fields are invalid."
                )
            if any(field in item for field in UPDATE_FIELDS) and (
                "form_fields" not in item
                or not all(field in item for field in UPDATE_FIELDS)
                or any(
                    not isinstance(item[field], str) or not item[field].strip()
                    for field in UPDATE_FIELDS
                )
            ):
                raise ContentFormatError(
                    "A Little Tree parenting scenario update action is invalid."
                )
            if any(field in item for field in VISUAL_FIELDS) and (
                not all(field in item for field in VISUAL_FIELDS)
                or any(
                    not isinstance(item[field], str) or not item[field].strip()
                    for field in VISUAL_FIELDS
                )
            ):
                raise ContentFormatError(
                    "A Little Tree parenting scenario visual metadata is invalid."
                )

            scenario: dict[str, Any] = {
                field: item[field].strip() for field in SCENARIO_FIELDS
            }
            if "action_label" in item:
                scenario["action_label"] = item["action_label"].strip()
            if "editable" in item:
                scenario["editable"] = item["editable"]
            if "questions" in item:
                scenario["questions"] = [
                    {field: question[field].strip() for field in QUESTION_FIELDS}
                    for question in item["questions"]
                ]
            for field in DEMO_FIELDS:
                if field in item:
                    scenario[field] = item[field].strip()
            if "form_fields" in item:
                scenario["form_fields"] = [
                    {
                        **{
                            field: form_field[field].strip()
                            for field in FORM_FIELD_STRING_FIELDS
                        },
                        "inspirations": [
                            inspiration.strip()
                            for inspiration in form_field["inspirations"]
                        ],
                    }
                    for form_field in item["form_fields"]
                ]
            for field in UPDATE_FIELDS:
                if field in item:
                    scenario[field] = item[field].strip()
            for field in VISUAL_FIELDS:
                if field in item:
                    scenario[field] = item[field].strip()
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


def get_parenting_scenarios() -> list[dict[str, Any]]:
    return _default_skill.get_parenting_scenarios()
