from __future__ import annotations

import inspect
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from skills.ipas_ai_application_planner import DataUnavailableError


ROOT = Path(__file__).resolve().parents[1]


def embedded_json(html: str, element_id: str):
    match = re.search(
        rf'<script id="{re.escape(element_id)}" type="application/json">(.*?)</script>',
        html,
        flags=re.S,
    )
    if not match:
        raise AssertionError(f"missing embedded JSON element: {element_id}")
    return json.loads(match.group(1))


class IpasWebTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_course_page_returns_200_with_formal_title(self):
        response = self.client.get("/ipas")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>iPAS AI 應用規劃師｜AI Learning Platform</title>", html)
        self.assertIn("iPAS AI 應用規劃師正式課程", html)

    def test_page_contains_seven_ordered_formal_chapters(self):
        response = self.client.get("/ipas")
        chapters = embedded_json(response.get_data(as_text=True), "chapter-data")

        self.assertEqual(len(chapters), 7)
        self.assertEqual([item["chapter_id"] for item in chapters], [f"CH-{number:02d}" for number in range(1, 8)])
        self.assertEqual([item["order"] for item in chapters], list(range(1, 8)))
        self.assertTrue(all(item["content_markdown"] for item in chapters))

    def test_page_contains_fifty_six_public_questions(self):
        response = self.client.get("/ipas")
        questions = embedded_json(response.get_data(as_text=True), "question-data")

        self.assertEqual(len(questions), 56)
        self.assertEqual(questions[0]["question_id"], "L111-Q001")
        self.assertEqual(questions[-1]["question_id"], "L123-Q008")

    def test_browser_payload_never_contains_answers_or_explanations(self):
        response = self.client.get("/ipas")
        html = response.get_data(as_text=True)
        questions = embedded_json(html, "question-data")
        chapters = embedded_json(html, "chapter-data")

        self.assertTrue(all("correct_answer" not in item for item in questions))
        self.assertTrue(all("explanation" not in item for item in questions))
        self.assertNotIn('"correct_answer"', html)
        self.assertNotIn('"explanation"', html)
        self.assertTrue(all("答案與解析" not in item["content_markdown"] for item in chapters))

    def test_web_files_no_longer_depend_on_legacy_l111_json(self):
        paths = (ROOT / "main.py", ROOT / "templates" / "ipas.html", ROOT / "assets" / "ipas.js")
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertNotIn("l111_knowledge.json", combined)
        self.assertNotIn("l111_questions.json", combined)
        self.assertNotIn("knowledge-data", combined)

    def test_route_uses_skill_api_without_markdown_loader(self):
        source = inspect.getsource(main.ipas_page)

        self.assertIn("ipas_ai_skill.get_course_info()", source)
        self.assertIn("ipas_ai_skill.get_chapters()", source)
        self.assertIn("ipas_ai_skill.get_questions()", source)
        self.assertNotIn("open(", source)
        self.assertNotIn("read_text", source)
        self.assertNotIn(".md", source)

    def test_correct_answer_is_graded_by_backend(self):
        response = self.client.post(
            "/api/ipas/answer",
            json={"question_id": "L111-Q001", "answer": "A"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["correct"])
        self.assertEqual(payload["correct_answer"], "A")
        self.assertTrue(payload["explanation"])

    def test_wrong_answer_returns_false_and_explanation(self):
        response = self.client.post(
            "/api/ipas/answer",
            json={"question_id": "L111-Q001", "answer": "D"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["correct"])
        self.assertEqual(payload["correct_answer"], "A")
        self.assertTrue(payload["explanation"])

    def test_missing_fields_return_consistent_400(self):
        cases = (
            ({"answer": "A"}, "missing_question_id"),
            ({"question_id": "L111-Q001"}, "missing_answer"),
        )
        for payload, expected_error in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/ipas/answer", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], expected_error)

    def test_invalid_answer_returns_400(self):
        response = self.client.post(
            "/api/ipas/answer",
            json={"question_id": "L111-Q001", "answer": "E"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_answer")

    def test_unknown_question_returns_404(self):
        response = self.client.post(
            "/api/ipas/answer",
            json={"question_id": "L111-Q999", "answer": "A"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json(),
            {"ok": False, "error": "question_not_found", "message": "找不到指定的題目。"},
        )

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            "/api/ipas/answer",
            data="{not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_json")

    def test_non_json_request_returns_400(self):
        response = self.client.post("/api/ipas/answer", data="question_id=L111-Q001&answer=A")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_json")

    def test_missing_materials_render_understandable_error(self):
        with patch.object(
            main.ipas_ai_skill,
            "get_course_info",
            side_effect=DataUnavailableError("D:\\private\\missing.md"),
        ):
            response = self.client.get("/ipas")

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("課程暫時無法載入", html)
        self.assertNotIn("private", html)

    def test_grading_error_does_not_leak_internal_details(self):
        with patch.object(main.ipas_ai_skill, "submit_answer", side_effect=RuntimeError("D:\\secret\\answers.md")):
            response = self.client.post(
                "/api/ipas/answer",
                json={"question_id": "L111-Q001", "answer": "A"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "internal_error")
        self.assertNotIn("secret", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
