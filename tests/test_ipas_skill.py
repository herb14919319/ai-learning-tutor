from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from agents.router import route
from skills.ipas_ai_application_planner.skill import (
    DataUnavailableError,
    IpasAiApplicationPlannerSkill,
)
from skills.ipas_ai_application_planner.scripts.process_sources import process
from skills.registry import get_skill, get_skill_metadata, list_skills


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "skills" / "ipas_ai_application_planner" / "knowledge" / "processed"


class IpasSkillTest(unittest.TestCase):
    def setUp(self):
        self.skill = IpasAiApplicationPlannerSkill(PROCESSED, rng=random.Random(7))

    def test_skill_is_registered_and_loadable(self):
        metadata = get_skill_metadata("ipas_ai_application_planner")

        self.assertIsNotNone(metadata)
        self.assertTrue(metadata.enabled)
        self.assertEqual(metadata.entrypoint, "skills.ipas_ai_application_planner")
        self.assertIn("query_l111_concept", metadata.capabilities)
        self.assertIn("ipas_ai_application_planner", [item.name for item in list_skills()])
        self.assertIsNotNone(get_skill("ipas_ai_application_planner"))

    def test_l111_query_returns_grounded_answer(self):
        item = self.skill.query_concept("HITL 是什麼？")

        self.assertIsNotNone(item)
        self.assertEqual(item["knowledge_id"], "L111-K006")
        self.assertTrue(item["source_references"])
        self.assertIn("SRC-CORE-001", self.skill.answer("L111 HITL 是什麼？"))

    def test_random_question_hides_answer_and_has_sources(self):
        question = self.skill.get_random_question()

        self.assertNotIn("correct_answer", question)
        self.assertEqual(len(question["options"]), 4)
        self.assertTrue(question["source_references"])

    def test_correct_answer_is_accepted(self):
        result = self.skill.submit_answer("L111-Q001", "A")

        self.assertTrue(result["correct"])
        self.assertEqual(result["correct_answer"], "A")

    def test_wrong_answer_returns_explanation_and_sources(self):
        result = self.skill.submit_answer("L111-Q001", "D")

        self.assertFalse(result["correct"])
        self.assertTrue(result["explanation"])
        self.assertTrue(result["source_references"])
        rendered = self.skill.answer("L111-Q001 答案 D")
        self.assertIn("答錯了", rendered)
        self.assertIn("解析", rendered)

    def test_answer_without_question_id_is_rejected_safely(self):
        answer = self.skill.answer("答案選 B。")

        self.assertIn("無法判定", answer)
        self.assertIn("題號", answer)
        self.assertNotIn("正確答案", answer)

    def test_question_source_requires_or_uses_question_id(self):
        self.assertIn("請附上題號", self.skill.answer("這題的來源是什麼？"))
        grounded = self.skill.answer("L111-Q001 來源")
        self.assertIn("SRC-CORE-001", grounded)
        self.assertIn("1.1 AI 的能力範疇分類", grounded)

    def test_supervision_comparison_includes_all_three_modes(self):
        answer = self.skill.answer("HITL、HOTL、HOOTL 差在哪裡？")

        self.assertIn("HITL（", answer)
        self.assertIn("HOTL（", answer)
        self.assertIn("HOOTL（", answer)
        self.assertIn("SRC-CORE-001", answer)

    def test_missing_processed_material_does_not_pretend_success(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_skill = IpasAiApplicationPlannerSkill(Path(directory))
            with self.assertRaises(DataUnavailableError):
                missing_skill.get_key_points()
            self.assertIn("缺少", missing_skill.answer("L111 的 HITL 是什麼？"))

    def test_source_processor_refuses_incomplete_material_set(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            with self.assertRaises(FileNotFoundError):
                process(Path(source), Path(output))
            self.assertEqual(list(Path(output).iterdir()), [])

    def test_processed_payloads_have_expected_counts_and_review_status(self):
        manifest = json.loads((PROCESSED / "source_manifest.json").read_text(encoding="utf-8"))
        knowledge = json.loads((PROCESSED / "l111_knowledge.json").read_text(encoding="utf-8"))
        questions = json.loads((PROCESSED / "l111_questions.json").read_text(encoding="utf-8"))

        self.assertEqual(len(knowledge), 10)
        self.assertEqual(len(questions), 10)
        self.assertEqual(len(manifest), 3)
        self.assertTrue(all(item["parse_status"] == "success" for item in manifest))
        self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest))
        self.assertTrue(all(item["review_status"] == "pending_review" for item in knowledge))
        self.assertTrue(all(item["review_status"] == "pending_review" for item in questions))
        self.assertTrue(all(item["question_type"] == "single_choice_generated" for item in questions))

    def test_router_prioritizes_ipas_without_breaking_existing_routes(self):
        self.assertEqual(route("請解釋 L111 的 XAI")["skill"], "ipas_ai_application_planner")
        self.assertEqual(route("我要準備 iPAS AI 應用規劃師")["skill"], "ipas_ai_application_planner")
        self.assertEqual(route("什麼是弱 AI？")["skill"], "ipas_ai_application_planner")
        self.assertEqual(route("Strong AI 跟 AGI 一樣嗎？")["skill"], "ipas_ai_application_planner")
        self.assertEqual(route("AI、機器學習與深度學習有什麼關係？")["skill"], "ipas_ai_application_planner")
        self.assertEqual(route("答案選 B。")["skill"], "general")
        self.assertEqual(route("這題的來源是什麼？")["skill"], "general")
        self.assertEqual(route("什麼是 AI？")["skill"], "hungyi_lee")
        self.assertEqual(route("什麼是 Transformer？")["skill"], "hungyi_lee")
        self.assertEqual(route("深度學習模型有哪些？")["skill"], "hungyi_lee")
        self.assertEqual(route("basic AI tutorial")["skill"], "hungyi_lee")
        self.assertEqual(route("今天晚餐吃什麼？")["skill"], "general")


if __name__ == "__main__":
    unittest.main()
