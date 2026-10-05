"""R3.1: the cybersecurity manifest covers its existing I11-ASSET and I11-PHYS slices, and nothing more."""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from router_guard import manifest_scope_terms, route_learning_boundary
from skills.registry import DISCOVERY_RESULT, get_runtime

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "skills" / "ipas_cybersecurity" / "skill.json"
SLICE_TERMS = ["I11-ASSET", "資訊資產", "I11-PHYS", "實體安全", "周邊安全", "安全區域設計", "fail secure"]


class CybersecuritySliceRoutingTest(unittest.TestCase):
    ASSET_QUESTIONS = {
        "資訊資產清冊要記錄哪些欄位？": "I11-ASSET-001",
        "資訊資產價值分類 A 級和 B 級差在哪？": "I11-ASSET-001",
    }
    PHYS_QUESTIONS = {
        "實體安全有哪些支持系統？": "I11-PHYS-001",
        "周邊安全有哪些控制？": "I11-PHYS-004",
        "門的 fail secure 是什麼？": "I11-PHYS-008",
        "安全區域設計要注意什麼？": "I11-PHYS-001",
    }

    def setUp(self):
        self.runtime = get_runtime()

    def route(self, text):
        return self.runtime.route(self.runtime.normalize_request(text))["skill"]

    def assert_reaches_cybersecurity(self, text):
        self.assertTrue(route_learning_boundary(text).allowed, text)
        self.assertEqual(self.route(text), "ipas_cybersecurity", text)

    def test_asset_and_physical_questions_route_to_cybersecurity(self):
        for text in [*self.ASSET_QUESTIONS, *self.PHYS_QUESTIONS, "I11-ASSET-Q001 答案 A", "I11-PHYS-Q001 答案 A"]:
            with self.subTest(text=text):
                self.assert_reaches_cybersecurity(text)

    def test_routed_questions_are_answered_from_the_matching_slice(self):
        skill = main.ipas_cyber_skill
        for text, chunk_id in {**self.ASSET_QUESTIONS, **self.PHYS_QUESTIONS}.items():
            with self.subTest(text=text):
                self.assertEqual(skill.query_concept(text)["chunk_id"], chunk_id)
        with patch.object(main.tutor_agent, "_general_teaching_answer") as general:
            reply = main.generate_tutor_answer("I11-PHYS-Q001 答案 A", user_id="r31-user")
        general.assert_not_called()
        self.assertIn("正確答案", reply)
        self.assertIn("第 84 頁", reply)

    def test_rollback_flag_restores_previous_rejection(self):
        with patch.dict(os.environ, {"GUARD_USE_MANIFEST_TERMS": "false"}):
            for text in [*self.ASSET_QUESTIONS, *self.PHYS_QUESTIONS]:
                with self.subTest(text=text):
                    self.assertFalse(route_learning_boundary(text).allowed)


class CommonWordsDoNotWidenScopeTest(unittest.TestCase):
    UNRELATED = (
        "How do I sell an asset?", "asset allocation for retirement", "公司資產負債表怎麼看", "資產配置怎麼做",
        "physical exercise plan", "physical therapy near me", "fail safe 設計原則是什麼",
        "遊戲裡的安全區域是什麼", "社區門禁卡壞了怎麼辦", "機房空調太冷", "實體店面在哪裡",
    )

    def test_generic_uses_are_still_rejected_and_unrouted(self):
        runtime = get_runtime()
        for text in self.UNRELATED:
            with self.subTest(text=text):
                guard = route_learning_boundary(text)
                self.assertFalse(guard.allowed)
                self.assertEqual(guard.intent, "unknown")
                self.assertEqual(runtime.route(runtime.normalize_request(text))["skill"], "general")

    def test_only_specific_slice_terms_were_added(self):
        keywords = json.loads(MANIFEST.read_text(encoding="utf-8"))["keywords"]
        self.assertEqual(keywords[-len(SLICE_TERMS):], SLICE_TERMS)
        generic = {"asset", "assets", "physical", "資產", "實體", "門禁", "機房", "空調", "安全區域", "fail safe"}
        self.assertFalse(generic & {k.lower() for k in keywords})


class OtherSkillsUnchangedTest(unittest.TestCase):
    def test_existing_routes_are_unchanged(self):
        runtime = get_runtime()
        expected = {
            "CIA Triad 是什麼": "ipas_cybersecurity",
            "風險評鑑流程": "ipas_cybersecurity",
            "資安風險是什麼": "ipas_cybersecurity",
            "L111 考什麼": "ipas_ai_application_planner",
            "HITL 跟 HOTL 差在哪": "ipas_ai_application_planner",
            "iPAS AI 弱AI 是什麼": "ipas_ai_application_planner",
            "Transformer 是什麼": "hungyi_lee",
            "RAG 跟 fine-tune 差在哪？": "hungyi_lee",
            "我想學生成式AI": "hungyi_lee",
        }
        for text, skill in expected.items():
            with self.subTest(text=text):
                self.assertTrue(route_learning_boundary(text).allowed)
                self.assertEqual(runtime.route(runtime.normalize_request(text))["skill"], skill)

    def test_only_the_cybersecurity_manifest_gained_terms(self):
        by_skill = {m.name: m for m in DISCOVERY_RESULT.manifests}
        planner = json.loads((ROOT / "skills/ipas_ai_application_planner/skill.json").read_text(encoding="utf-8"))
        hungyi = json.loads((ROOT / "skills/hung-yi-lee-skill/skill.json").read_text(encoding="utf-8"))
        self.assertEqual((len(planner["domains"]), len(planner["keywords"]), len(planner["aliases"])), (2, 21, 2))
        self.assertEqual((len(hungyi["domains"]), len(hungyi["keywords"]), len(hungyi["aliases"])), (5, 17, 2))
        self.assertEqual(len(manifest_scope_terms()), 60 + len(SLICE_TERMS))
        for web_only in ("ipas_net_zero_planner", "little_tree"):
            with self.subTest(skill=web_only):
                self.assertFalse(by_skill[web_only].enabled)
                self.assertEqual(by_skill[web_only].skill_type, "web")
        self.assertFalse(route_learning_boundary("淨零排放是什麼").allowed)


if __name__ == "__main__":
    unittest.main()
