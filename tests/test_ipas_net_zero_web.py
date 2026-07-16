from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import main
from skills.ipas_net_zero_planner import DataUnavailableError, get_chapters


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_FILE_HASHES = {
    "templates/ipas.html": "273d19c222eaa25178aa9bd4702d22278b38d367009ec9720a1058bf770a603f",
    "assets/ipas.js": "510c8c10a17649dff2e6dc5a8ea23274c12945262827a0af61042437c19d4431",
    "assets/ipas.css": "ba14f06cde01f4fae2bdd8375af10bd093ea31c64b77ce73f7db6ca73ea8f908",
}


def embedded_json(html: str, element_id: str):
    match = re.search(
        rf'<script id="{re.escape(element_id)}" type="application/json">(.*?)</script>',
        html,
        flags=re.S,
    )
    if not match:
        raise AssertionError(f"missing embedded JSON element: {element_id}")
    return json.loads(match.group(1))


class IpasNetZeroWebTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_course_page_returns_200_with_correct_title(self):
        response = self.client.get("/ipas/net-zero-planner")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>iPAS 淨零碳規劃師｜AI Learning Platform</title>", html)
        self.assertIn("iPAS 淨零碳規劃師學習平台", html)

    def test_page_contains_eight_ordered_chapters_and_36_cards(self):
        response = self.client.get("/ipas/net-zero-planner")
        chapters = embedded_json(response.get_data(as_text=True), "chapter-data")

        self.assertEqual(len(chapters), 8)
        self.assertEqual([item["chapter_id"] for item in chapters], [f"ch{number:02d}" for number in range(1, 9)])
        self.assertEqual(sum(len(item["cards"]) for item in chapters), 36)
        self.assertTrue(all(item["markdown"] for item in chapters))

    def test_browser_question_data_never_contains_answers_or_explanations(self):
        response = self.client.get("/ipas/net-zero-planner")
        html = response.get_data(as_text=True)
        questions = embedded_json(html, "question-data")

        self.assertEqual(len(questions), 8)
        self.assertTrue(all("correct_answer" not in item for item in questions))
        self.assertTrue(all("explanation" not in item for item in questions))
        self.assertNotIn('"correct_answer"', html)

    def test_valid_card_route_returns_image(self):
        card_path = get_chapters()[0]["cards"][0].removeprefix("cards/")
        response = self.client.get(f"/ipas/net-zero-planner/cards/{quote(card_path, safe='/')}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_missing_card_returns_404(self):
        response = self.client.get("/ipas/net-zero-planner/cards/ch01/not-found.png")
        self.assertEqual(response.status_code, 404)

    def test_card_path_traversal_cannot_leave_cards_directory(self):
        attempts = (
            "/ipas/net-zero-planner/cards/../knowledge/processed/ch01_climate_governance.md",
            "/ipas/net-zero-planner/cards/ch01/../../knowledge/processed/ch01_climate_governance.md",
            "/ipas/net-zero-planner/cards/%2e%2e/knowledge/processed/ch01_climate_governance.md",
        )
        for url in attempts:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_correct_answer_is_graded_by_backend(self):
        response = self.client.post(
            "/api/ipas/net-zero-planner/answer",
            json={"question_id": "NZ-Q001", "answer": "A"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["correct"])
        self.assertEqual(payload["correct_answer"], "A")
        self.assertTrue(payload["explanation"])
        self.assertTrue(payload["source_references"])

    def test_wrong_answer_returns_explanation_and_sources(self):
        response = self.client.post(
            "/api/ipas/net-zero-planner/answer",
            json={"question_id": "NZ-Q001", "answer": "B"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["correct"])
        self.assertEqual(payload["correct_answer"], "A")
        self.assertTrue(payload["explanation"])
        self.assertEqual(payload["source_references"][0]["locator"], "knowledge/processed/ch01_climate_governance.md")

    def test_invalid_question_id_returns_consistent_404(self):
        response = self.client.post(
            "/api/ipas/net-zero-planner/answer",
            json={"question_id": "NZ-Q999", "answer": "A"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"ok": False, "error": "question_not_found", "message": "找不到指定的題目。"})

    def test_missing_fields_and_invalid_answer_return_400(self):
        cases = (
            ({"answer": "A"}, "missing_question_id"),
            ({"question_id": "NZ-Q001"}, "missing_answer"),
            ({"question_id": "NZ-Q001", "answer": "E"}, "invalid_answer"),
        )
        for payload, expected_error in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/ipas/net-zero-planner/answer", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.get_json()["ok"])
                self.assertEqual(response.get_json()["error"], expected_error)

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            "/api/ipas/net-zero-planner/answer",
            data="{not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_json")

    def test_skill_error_does_not_leak_local_paths(self):
        with patch.object(main.ipas_net_zero_skill, "submit_answer", side_effect=RuntimeError("D:\\secret\\file.md")):
            response = self.client.post(
                "/api/ipas/net-zero-planner/answer",
                json={"question_id": "NZ-Q001", "answer": "A"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "internal_error")
        self.assertNotIn("secret", response.get_data(as_text=True))

    def test_missing_materials_render_understandable_error(self):
        with patch.object(
            main.ipas_net_zero_skill,
            "get_course_info",
            side_effect=DataUnavailableError("D:\\private\\missing"),
        ):
            response = self.client.get("/ipas/net-zero-planner")

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("課程暫時無法載入", html)
        self.assertNotIn("private", html)

    def test_existing_ipas_page_still_works(self):
        response = self.client.get("/ipas")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("iPAS AI 應用規劃師｜AI Learning Platform", html)
        self.assertIn("L111 人工智慧概念", html)

    def test_existing_ipas_ui_files_are_byte_identical(self):
        for relative_path, expected_hash in PROTECTED_FILE_HASHES.items():
            with self.subTest(path=relative_path):
                actual_hash = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
                self.assertEqual(actual_hash, expected_hash)


if __name__ == "__main__":
    unittest.main()
