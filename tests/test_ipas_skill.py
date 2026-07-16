from __future__ import annotations

import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path

from agents.router import route
from skills.ipas_ai_application_planner.skill import (
    ContentFormatError,
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

    def test_random_question_hides_answer_and_explanation(self):
        question = self.skill.get_random_question()

        self.assertNotIn("correct_answer", question)
        self.assertNotIn("explanation", question)
        self.assertEqual(len(question["options"]), 4)
        self.assertIn("question_text", question)

    def test_correct_answer_is_accepted(self):
        result = self.skill.submit_answer("L111-Q001", "A")

        self.assertTrue(result["correct"])
        self.assertEqual(result["correct_answer"], "A")

    def test_wrong_answer_returns_explanation_and_sources(self):
        result = self.skill.submit_answer("L111-Q001", "D")

        self.assertFalse(result["correct"])
        self.assertTrue(result["explanation"])
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
        self.assertIn("人工智慧概念", grounded)
        self.assertIn("ch01_ai_concepts.md", grounded)

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

    def test_formal_course_loads_seven_chapters_with_required_model(self):
        chapters = self.skill.get_chapters()

        self.assertEqual(len(chapters), 7)
        required = {
            "chapter_id",
            "lesson_code",
            "title",
            "source_file",
            "order",
            "content_markdown",
            "question_count",
        }
        self.assertTrue(all(required <= chapter.keys() for chapter in chapters))
        self.assertTrue(all(chapter["content_markdown"] for chapter in chapters))

    def test_formal_chapter_order_follows_index(self):
        chapters = self.skill.get_chapters()

        self.assertEqual([item["order"] for item in chapters], list(range(1, 8)))
        self.assertEqual(
            [item["lesson_code"] for item in chapters],
            ["L111", "L112", "L113", "L114", "L121", "L122", "L123"],
        )

    def test_each_chapter_has_eight_questions(self):
        for chapter in self.skill.get_chapters():
            with self.subTest(chapter_id=chapter["chapter_id"]):
                self.assertEqual(chapter["question_count"], 8)
                self.assertEqual(len(self.skill.get_questions(chapter["chapter_id"])), 8)

    def test_formal_question_count_is_fifty_six(self):
        info = self.skill.get_course_info()
        questions = self.skill.get_questions()

        self.assertEqual(info["chapter_count"], 7)
        self.assertEqual(info["question_count"], 56)
        self.assertEqual(len(questions), 56)
        self.assertEqual(questions[0]["question_id"], "L111-Q001")
        self.assertEqual(questions[-1]["question_id"], "L123-Q008")

    def test_public_questions_never_expose_answers_or_explanations(self):
        serialized = json.dumps(self.skill.get_questions(), ensure_ascii=False)

        self.assertNotIn("correct_answer", serialized)
        self.assertNotIn("answer_index", serialized)
        self.assertNotIn("explanation", serialized)

    def test_chapter_content_excludes_quiz_and_answer_sections(self):
        for chapter in self.skill.get_chapters():
            with self.subTest(chapter_id=chapter["chapter_id"]):
                self.assertNotIn("### 自我測驗", chapter["content_markdown"])
                self.assertNotIn("答案與解析", chapter["content_markdown"])

    def test_backend_grades_formal_correct_answer(self):
        result = self.skill.submit_answer("L112-Q001", "C")

        self.assertTrue(result["correct"])
        self.assertEqual(result["correct_answer"], "C")
        self.assertEqual(result["chapter_id"], "CH-02")

    def test_backend_grades_formal_wrong_answer_with_explanation(self):
        result = self.skill.submit_answer("L112-Q001", "A")

        self.assertFalse(result["correct"])
        self.assertEqual(result["correct_answer"], "C")
        self.assertTrue(result["explanation"])

    def test_missing_chapter_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "找不到 iPAS 正式教材章節"):
            self.skill.get_chapter("CH-99")

    def test_malformed_markdown_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copy2(PROCESSED / "chapter_index.json", target / "chapter_index.json")
            index = json.loads((target / "chapter_index.json").read_text(encoding="utf-8"))
            for item in index:
                shutil.copy2(PROCESSED / item["source_file"], target / item["source_file"])

            broken = target / "ch02_data_processing_and_analysis.md"
            text = broken.read_text(encoding="utf-8")
            broken.write_text(text.replace("\nD. Transform\n", "\n", 1), encoding="utf-8")

            with self.assertRaises(ContentFormatError) as context:
                IpasAiApplicationPlannerSkill(target).get_chapters()

            message = str(context.exception)
            self.assertIn("CH-02", message)
            self.assertIn("題號 2", message)
            self.assertIn("缺少：D", message)

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
