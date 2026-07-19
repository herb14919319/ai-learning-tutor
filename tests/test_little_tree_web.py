from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from skills import little_tree


ROOT = Path(__file__).resolve().parents[1]
CATEGORY_TITLES = [
    "親子助手",
    "學習助手",
    "創作助手",
    "生活助手",
    "工作助手",
    "陪伴助手",
    "創業助手",
]
CATEGORY_IDS = [
    "parenting",
    "learning",
    "creative",
    "life",
    "work",
    "companion",
    "business",
]
SCENARIO_TITLES = [
    "一起創作睡前故事",
    "把孩子畫的角色變成 AI 角色",
    "設計親子共讀活動",
]
SCENARIO_FIELDS = {"id", "title", "description", "prompt"}


class LittleTreeContentTest(unittest.TestCase):
    def test_categories_file_contains_the_seven_fixed_categories(self):
        categories = little_tree.get_categories()

        self.assertEqual([item["id"] for item in categories], CATEGORY_IDS)
        self.assertEqual([item["title"] for item in categories], CATEGORY_TITLES)
        self.assertTrue(
            all(
                set(item) == {"id", "title", "description", "icon", "route"}
                for item in categories
            )
        )
        self.assertTrue(
            all(item["route"] == f"/little-tree/{item['id']}" for item in categories)
        )

    def test_fixed_content_directories_exist(self):
        content_root = ROOT / "skills" / "little_tree" / "content"

        for category_id in CATEGORY_IDS:
            with self.subTest(category_id=category_id):
                self.assertTrue((content_root / category_id).is_dir())

    def test_manifest_uses_existing_web_skill_contract(self):
        manifest = json.loads(
            (ROOT / "skills" / "little_tree" / "skill.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["skill_id"], "little_tree")
        self.assertEqual(manifest["status"], "active")
        self.assertEqual(manifest["skill_type"], "web")
        self.assertEqual(manifest["content_root"], "content")
        self.assertNotIn("entrypoint", manifest)

    def test_parenting_file_contains_three_exploratory_prompts(self):
        scenarios = little_tree.get_parenting_scenarios()

        self.assertEqual([item["title"] for item in scenarios], SCENARIO_TITLES)
        self.assertTrue(all(set(item) == SCENARIO_FIELDS for item in scenarios))
        self.assertTrue(all("請先" in item["prompt"] for item in scenarios))
        self.assertTrue(all("確認" in item["prompt"] for item in scenarios))
        self.assertTrue(all("繁體中文" in item["prompt"] for item in scenarios))

    def test_invalid_parenting_content_is_rejected(self):
        def item(item_id: str) -> dict[str, str]:
            return {
                "id": item_id,
                "title": f"情境 {item_id}",
                "description": "說明",
                "prompt": "請先詢問必要資訊，確認後再繼續，並使用繁體中文。",
            }

        cases = (
            {"invalid": "not-an-array"},
            [item("one"), item("two")],
            [item("one"), item("two"), {"id": "missing-fields"}],
            [item("one"), item("two"), {**item("three"), "prompt": " "}],
            [item("duplicate"), item("duplicate"), item("three")],
        )

        for payload in cases:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                parenting_dir = Path(directory) / "parenting"
                parenting_dir.mkdir()
                (parenting_dir / "scenarios.json").write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                skill = little_tree.LittleTreeSkill(Path(directory))

                with self.assertRaises(little_tree.ContentFormatError):
                    skill.get_parenting_scenarios()


class LittleTreeWebTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_home_page_returns_frontend_entry(self):
        response = self.client.get("/little-tree")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>Little Tree｜AI Prompt Navigator</title>", html)
        self.assertIn('data-categories-url="/api/little-tree/categories"', html)
        self.assertIn(
            'data-parenting-scenarios-url="/api/little-tree/categories/parenting/scenarios"',
            html,
        )
        self.assertIn("/assets/little_tree.css", html)
        self.assertIn("/assets/little_tree.js", html)

    def test_categories_endpoint_returns_seven_public_cards(self):
        with patch.object(main, "ask_gpt") as ask_gpt:
            response = self.client.get("/api/little-tree/categories")

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual([item["title"] for item in payload["categories"]], CATEGORY_TITLES)
        ask_gpt.assert_not_called()

    def test_parenting_scenarios_endpoint_returns_three_complete_items(self):
        with patch.object(main, "ask_gpt") as ask_gpt:
            response = self.client.get(
                "/api/little-tree/categories/parenting/scenarios"
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["scenarios"]],
            SCENARIO_TITLES,
        )
        self.assertTrue(
            all(set(item) == SCENARIO_FIELDS for item in payload["scenarios"])
        )
        ask_gpt.assert_not_called()

    def test_parenting_scenarios_endpoint_is_read_only(self):
        response = self.client.post(
            "/api/little-tree/categories/parenting/scenarios",
            json={"prompt": "replacement"},
        )

        self.assertEqual(response.status_code, 405)

    def test_frontend_has_parenting_prompt_and_copy_flow(self):
        source = (ROOT / "assets" / "little_tree.js").read_text(encoding="utf-8")

        self.assertIn("fetch(categoriesUrl", source)
        self.assertIn("payload.categories.map(createCategoryCard)", source)
        self.assertIn("fetch(parentingScenariosUrl", source)
        self.assertIn("parentingScenarios.map(createScenarioCard)", source)
        self.assertIn('category.id === "parenting"', source)
        self.assertIn("promptContent.textContent = scenario.prompt", source)
        self.assertIn("navigator.clipboard.writeText(selectedPrompt)", source)
        self.assertIn("Prompt 已複製", source)
        self.assertIn("Coming Soon", source)
        self.assertNotIn("/web-chat", source)
        self.assertNotIn("/answer", source)

    def test_other_categories_still_use_coming_soon(self):
        source = (ROOT / "assets" / "little_tree.js").read_text(encoding="utf-8")

        self.assertIn("showComingSoon(category)", source)
        self.assertIn('if (category.id === "parenting")', source)

    def test_unavailable_content_returns_safe_503(self):
        with patch.object(
            main.little_tree_skill,
            "get_categories",
            side_effect=little_tree.DataUnavailableError("D:\\private\\categories.json"),
        ):
            response = self.client.get("/api/little-tree/categories")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "skill_unavailable")
        self.assertNotIn("private", response.get_data(as_text=True))

    def test_internal_error_does_not_leak_local_details(self):
        with patch.object(
            main.little_tree_skill,
            "get_categories",
            side_effect=RuntimeError("D:\\secret\\categories.json"),
        ):
            response = self.client.get("/api/little-tree/categories")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "internal_error")
        self.assertNotIn("secret", response.get_data(as_text=True))

    def test_invalid_parenting_content_returns_safe_503(self):
        with patch.object(
            main.little_tree_skill,
            "get_parenting_scenarios",
            side_effect=little_tree.ContentFormatError("D:\\private\\scenarios.json"),
        ):
            response = self.client.get(
                "/api/little-tree/categories/parenting/scenarios"
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "skill_unavailable")
        self.assertNotIn("private", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
