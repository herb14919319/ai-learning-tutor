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
    "畫出我心中的科教館",
]
SCENARIO_FIELDS = {"id", "title", "description", "prompt"}
SCIENCE_MUSEUM_PROMPT = """請根據孩子自己的想法，畫出一座心中的未來科教館。

科教館的外觀是【科教館外觀】。
館內最神奇的設施是【神奇設施】。
希望大家在這裡學到【學習主題】。
館中加入【永續元素】，讓環境變得更好。
為科教館70歲生日安排【生日慶祝方式】。
孩子希望畫面呈現【畫面感覺】。

請以科教館建築為唯一且最清楚的畫面主角，建築約占畫面60～70%，完整呈現外觀，不被人物、背景或裝飾遮擋。採單一主體、正面或容易理解的簡單視角，保留大量留白與乾淨背景，讓人一眼看出畫面重點；不要使用複雜透視、多重場景或滿版細節。

將孩子描述的神奇設施自然融入建築本體，像是從建築延伸或成為建築的一部分，不要另外畫成獨立世界。將孩子填寫的永續元素直接表現在建築設計上，不需另外加上圖解或說明。

70歲生日慶祝元素只需少量點綴在背景或角落，優先呈現孩子填寫的慶祝方式，不可搶走建築主體。畫面可以不出現人物；只有孩子的描述確實需要人物時，最多畫2～3位小朋友，不要出現大量群眾。

保留孩子指定的畫面感覺，同時以適合國小學生觀察與自行創作的兒童繪本方式呈現：線條清楚、色彩柔和、大面積色塊、造型簡單。避免大量人物、複雜背景、過多裝飾、電影海報感、超寫實電影場景與滿版細節。目標是構圖清楚、容易理解的創作參考圖，不是最華麗或最複雜的AI圖片。

作品以國立臺灣科學教育館70週年館慶為背景，將「科教70・永續∞」轉化為視覺氛圍，自然融合STEAM精神、科學探索、永續環境與歡樂生日慶典；不要把主題字樣畫在畫面中。

完全保留孩子填寫的創意，不改寫孩子的核心想法，也不新增孩子未提及的核心設定。畫面中不要出現任何文字、字母、數字、Logo、標語、海報或其他文字內容。"""
SCIENCE_MUSEUM_FIELD_LABELS = [
    "我的科教館長什麼樣子？",
    "裡面有哪些最神奇的設施？",
    "我希望大家在這裡學到什麼？",
    "我想加入哪些永續元素？",
    "我想怎麼替科教館70歲生日慶祝？",
    "我希望畫面呈現什麼感覺？",
]


class LittleTreeContentTest(unittest.TestCase):
    def test_categories_file_remains_compatible_with_phase_one_contract(self):
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

    def test_fixed_content_directories_remain_available(self):
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

    def test_parenting_file_contains_existing_prompts_and_science_museum_activity(self):
        scenarios = little_tree.get_parenting_scenarios()

        self.assertEqual([item["title"] for item in scenarios], SCENARIO_TITLES)
        self.assertTrue(all(SCENARIO_FIELDS.issubset(item) for item in scenarios))
        self.assertTrue(all("請先" in item["prompt"] for item in scenarios[:3]))
        self.assertTrue(all("繁體中文" in item["prompt"] for item in scenarios[:3]))

        museum = scenarios[3]
        self.assertEqual(museum["id"], "future-science-museum")
        self.assertEqual(
            museum["description"],
            "發揮想像力，設計一座屬於你的未來科教館，讓 AI 幫你把想像畫出來！",
        )
        self.assertEqual(museum["action_label"], "開始創作")
        self.assertTrue(museum["editable"])
        self.assertEqual(museum["icon"], "🚀")
        self.assertEqual(museum["card_class"], "museum-card")
        self.assertEqual(
            [form_field["label"] for form_field in museum["form_fields"]],
            SCIENCE_MUSEUM_FIELD_LABELS,
        )
        self.assertTrue(
            all(len(form_field["inspirations"]) == 4 for form_field in museum["form_fields"])
        )
        self.assertTrue(
            all(
                form_field["token"] in museum["prompt"]
                for form_field in museum["form_fields"]
            )
        )
        self.assertEqual(
            museum["demo_image"],
            "/assets/images/little_tree/science_museum_demo.png",
        )
        self.assertTrue(museum["demo_image_alt"])
        self.assertEqual(museum["demo_title"], "創作靈感 Demo")
        self.assertEqual(
            museum["demo_message"],
            "這只是參考喔！你可以比這更酷、更夢幻、更有想像力！",
        )
        self.assertEqual(museum["update_button_text"], "更新提示詞")
        self.assertEqual(
            museum["update_success_message"],
            "提示詞已更新！你還可以繼續修改內容。",
        )
        self.assertEqual(museum["prompt"], SCIENCE_MUSEUM_PROMPT)
        for required_theme in (
            "國立臺灣科學教育館70週年館慶",
            "科教70・永續∞",
            "STEAM精神",
            "科學探索",
            "永續環境",
            "歡樂生日慶典",
        ):
            with self.subTest(required_theme=required_theme):
                self.assertIn(required_theme, museum["prompt"])
        for forbidden_output in ("文字", "Logo", "標語", "海報"):
            with self.subTest(forbidden_output=forbidden_output):
                self.assertIn(forbidden_output, museum["prompt"])
        for composition_rule in (
            "建築約占畫面60～70%",
            "單一主體",
            "大量留白",
            "乾淨背景",
            "神奇設施自然融入建築本體",
            "永續元素直接表現在建築設計上",
            "最多畫2～3位小朋友",
            "兒童繪本",
            "線條清楚",
            "色彩柔和",
            "大面積色塊",
            "造型簡單",
            "不要出現大量群眾",
            "電影海報感",
            "超寫實電影場景",
        ):
            with self.subTest(composition_rule=composition_rule):
                self.assertIn(composition_rule, museum["prompt"])
        self.assertTrue(
            (
                ROOT / "assets" / "images" / "little_tree" / "science_museum_demo.png"
            ).is_file()
        )
        self.assertTrue(all("form_fields" not in scenario for scenario in scenarios[:3]))

    def test_invalid_parenting_content_is_rejected(self):
        def item(item_id: str) -> dict[str, str]:
            return {
                "id": item_id,
                "title": f"情境 {item_id}",
                "description": "簡短說明",
                "prompt": "請先詢問必要資訊，再用繁體中文逐步協助我探索。",
            }

        cases = (
            {"invalid": "not-an-array"},
            [item("one"), item("two"), item("three")],
            [item("one"), item("two"), item("three"), {"id": "missing-fields"}],
            [
                item("one"),
                item("two"),
                item("three"),
                {**item("four"), "prompt": " "},
            ],
            [item("duplicate"), item("duplicate"), item("three"), item("four")],
            [
                item("one"),
                item("two"),
                item("three"),
                {**item("four"), "editable": "yes"},
            ],
            [
                item("one"),
                item("two"),
                item("three"),
                {**item("four"), "form_fields": [{"id": "missing-fields"}]},
            ],
            [
                item("one"),
                item("two"),
                item("three"),
                {
                    **item("four"),
                    "form_fields": [
                        {
                            "id": "field",
                            "label": "問題",
                            "examples": "例子",
                            "placeholder": "請輸入",
                            "token": "【欄位】",
                            "inspirations": [],
                        }
                    ],
                },
            ],
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

    def test_home_page_returns_direct_parenting_entry(self):
        response = self.client.get("/little-tree")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>Little Tree 小樹｜親子 AI 探索入口</title>", html)
        self.assertIn(
            'data-scenarios-url="/api/little-tree/categories/parenting/scenarios"',
            html,
        )
        self.assertNotIn("data-categories-url", html)
        self.assertIn("今天想和 AI", html)
        self.assertIn("一起做什麼呢？", html)
        self.assertIn(
            "選一個喜歡的活動，複製提示詞，就可以和孩子一起開始探索。",
            html,
        )
        self.assertIn(
            "嗨，我是小樹！一起把孩子的想像力種進 AI 世界吧。",
            html,
        )
        self.assertIn("/assets/little_tree.css", html)
        self.assertIn("/assets/little_tree.js", html)

    def test_home_page_does_not_expose_general_category_ui_or_technical_copy(self):
        html = self.client.get("/little-tree").get_data(as_text=True)

        for copy in CATEGORY_TITLES[1:]:
            with self.subTest(copy=copy):
                self.assertNotIn(copy, html)
        for copy in (
            "Prompt Navigator",
            "Prompt Engineering",
            "Runtime Skill",
            "API",
            "Schema",
            "Generator",
            "Coming Soon",
        ):
            with self.subTest(copy=copy):
                self.assertNotIn(copy, html)

    def test_categories_endpoint_is_retained_for_contract_compatibility(self):
        with patch.object(main, "ask_gpt") as ask_gpt:
            response = self.client.get("/api/little-tree/categories")

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual([item["title"] for item in payload["categories"]], CATEGORY_TITLES)
        ask_gpt.assert_not_called()

    def test_parenting_scenarios_endpoint_returns_four_complete_items_without_model_call(self):
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
            all(SCENARIO_FIELDS.issubset(item) for item in payload["scenarios"])
        )
        museum = payload["scenarios"][3]
        self.assertEqual(museum["id"], "future-science-museum")
        self.assertEqual(museum["prompt"], SCIENCE_MUSEUM_PROMPT)
        self.assertTrue(museum["editable"])
        self.assertEqual(
            [form_field["label"] for form_field in museum["form_fields"]],
            SCIENCE_MUSEUM_FIELD_LABELS,
        )
        ask_gpt.assert_not_called()

    def test_science_museum_demo_image_is_served_from_local_assets(self):
        response = self.client.get(
            "/assets/images/little_tree/science_museum_demo.png"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/png")

    def test_parenting_scenarios_endpoint_is_read_only(self):
        response = self.client.post(
            "/api/little-tree/categories/parenting/scenarios",
            json={"prompt": "replacement"},
        )

        self.assertEqual(response.status_code, 405)

    def test_frontend_has_direct_prompt_copy_and_fallback_flow(self):
        source = (ROOT / "assets" / "little_tree.js").read_text(encoding="utf-8")

        self.assertIn("fetch(scenariosUrl", source)
        self.assertIn("payload.scenarios.map(createScenarioCard)", source)
        self.assertIn(
            'card.addEventListener("click", () => showPrompt(scenario))',
            source,
        )
        self.assertIn("promptView.hidden = false", source)
        self.assertIn("promptContent.textContent = scenario.prompt", source)
        self.assertIn(
            "navigator.clipboard.writeText(promptText)",
            source,
        )
        self.assertIn('document.execCommand("copy")', source)
        self.assertIn(
            "提示詞已複製，可以貼到你喜歡的 AI 繪圖工具囉！",
            source,
        )
        self.assertIn("scenario.editable", source)
        self.assertIn("promptEditor.value", source)
        self.assertIn("questionGuide.hidden = questions.length === 0", source)
        self.assertIn("scenario.demo_image", source)
        self.assertIn("demoImage.alt = scenario.demo_image_alt", source)
        self.assertIn('demoImage.addEventListener("error"', source)
        self.assertIn("scenario.form_fields", source)
        self.assertIn('document.createElement("label")', source)
        self.assertIn("input.placeholder = field.placeholder", source)
        self.assertIn("input.dataset.token = field.token", source)
        self.assertIn("field.inspirations.map((inspiration)", source)
        self.assertIn('card.className = "inspiration-card"', source)
        self.assertIn("input.value = inspiration", source)
        self.assertIn("input.focus()", source)
        self.assertIn('updatePrompt.addEventListener("click", updateSelectedPrompt)', source)
        self.assertIn("let updatedPrompt = selectedScenario.prompt", source)
        self.assertIn("input.value.trim() ? input.value : input.dataset.token", source)
        self.assertIn(
            "updatedPrompt.split(input.dataset.token).join(replacement)",
            source,
        )
        self.assertIn("promptEditor.value = updatedPrompt", source)
        self.assertIn(
            "setBuilderFeedback(selectedScenario.update_success_message",
            source,
        )
        self.assertIn("? promptEditor.value", source)
        self.assertIn("showLoadError()", source)
        self.assertIn("showHome()", source)
        self.assertNotIn("categoriesUrl", source)
        self.assertNotIn("Coming Soon", source)
        self.assertNotIn("/web-chat", source)
        self.assertNotIn("/answer", source)

    def test_prompt_detail_has_friendly_guidance_and_navigation(self):
        template = (ROOT / "templates" / "little_tree.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="prompt-title"', template)
        self.assertIn('id="prompt-description"', template)
        self.assertIn('id="prompt-content"', template)
        self.assertIn('id="prompt-editor"', template)
        self.assertIn('id="question-guide"', template)
        self.assertIn('id="question-list"', template)
        self.assertIn('id="demo-panel"', template)
        self.assertIn('id="demo-image"', template)
        self.assertIn('id="prompt-builder"', template)
        self.assertIn('id="form-fields"', template)
        self.assertIn('id="update-prompt"', template)
        self.assertIn('id="builder-feedback"', template)
        self.assertIn("沒有標準答案", template)
        self.assertIn("靈感小卡", template)
        self.assertIn('id="copy-prompt"', template)
        self.assertIn("複製提示詞", template)
        self.assertIn("回到探索首頁", template)
        self.assertIn(
            "複製後，貼到 ChatGPT、Gemini、Claude 或你常用的 AI，就可以開始囉！",
            template,
        )

    def test_accessibility_and_reduced_motion_hooks_are_present(self):
        template = (ROOT / "templates" / "little_tree.html").read_text(
            encoding="utf-8"
        )
        stylesheet = (ROOT / "assets" / "little_tree.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('role="status"', template)
        self.assertIn('aria-live="polite"', template)
        self.assertIn('role="alert"', template)
        self.assertIn('aria-busy="true"', template)
        self.assertIn(":focus-visible", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)

    def test_unavailable_categories_content_returns_safe_503(self):
        with patch.object(
            main.little_tree_skill,
            "get_categories",
            side_effect=little_tree.DataUnavailableError("D:\\private\\categories.json"),
        ):
            response = self.client.get("/api/little-tree/categories")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "skill_unavailable")
        self.assertNotIn("private", response.get_data(as_text=True))

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

    def test_parenting_internal_error_does_not_leak_local_details(self):
        with patch.object(
            main.little_tree_skill,
            "get_parenting_scenarios",
            side_effect=RuntimeError("D:\\secret\\scenarios.json"),
        ):
            response = self.client.get(
                "/api/little-tree/categories/parenting/scenarios"
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "internal_error")
        self.assertNotIn("secret", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
