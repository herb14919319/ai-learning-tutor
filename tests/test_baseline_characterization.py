"""R0 characterization tests.

These pin current behaviour before the incremental refactor (R1+). A test marked
CHARACTERIZATION documents behaviour that a later, approved step will change on
purpose; update it in that step, not silently.
"""

import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from linebot.v3.exceptions import InvalidSignatureError

import main
from app.channels import messenger_client
import runtime_telemetry
from router_guard import classify_intent, route_learning_boundary
from skills import ipas_ai_application_planner, ipas_cybersecurity, ipas_net_zero_planner
from skills.registry import get_runtime


ROOT = Path(__file__).resolve().parents[1]


class TelemetryIsolationTest(unittest.TestCase):
    def test_suite_never_targets_tracked_telemetry_file(self):
        tracked = (ROOT / runtime_telemetry.DEFAULT_TELEMETRY_PATH).resolve()
        active = Path(runtime_telemetry.TELEMETRY_PATH).resolve()
        self.assertNotEqual(
            active,
            tracked,
            "Tests would write production telemetry; run: python -m unittest discover -s tests -t .",
        )
        self.assertEqual(Path(os.environ["RUNTIME_TELEMETRY_PATH"]).resolve(), active)


class GuardRouterBoundaryCharacterizationTest(unittest.TestCase):
    """CHARACTERIZATION: the guard runs before skill routing (main._generate_tutor_answer).

    Today it rejects iPAS questions that the skill router would accept. The owner
    classified this as a bug; R3 makes enabled manifests part of the guard's scope.
    """

    BLOCKED_BUT_ROUTABLE = {
        "CIA Triad 是什麼": "ipas_cybersecurity",
        "資訊安全三目標": "ipas_cybersecurity",
        "風險評鑑流程": "ipas_cybersecurity",
        "I11-CIA-Q001 答案 A": "ipas_cybersecurity",
    }

    def setUp(self):
        self.runtime = get_runtime()

    def route(self, text):
        return self.runtime.route(self.runtime.normalize_request(text))["skill"]

    def test_ipas_cybersecurity_questions_are_routable_but_guard_rejected(self):
        for text, skill in self.BLOCKED_BUT_ROUTABLE.items():
            with self.subTest(text=text):
                self.assertEqual(self.route(text), skill)
                guard = route_learning_boundary(text)
                self.assertFalse(guard.allowed)
                self.assertEqual(guard.intent, "unknown")

    def test_ai_terms_pass_guard_and_reach_skills(self):
        self.assertTrue(route_learning_boundary("iPAS AI 弱AI 是什麼").allowed)
        self.assertEqual(self.route("iPAS AI 弱AI 是什麼"), "ipas_ai_application_planner")
        self.assertTrue(route_learning_boundary("Transformer 是什麼").allowed)
        self.assertEqual(self.route("Transformer 是什麼"), "hungyi_lee")

    def test_net_zero_is_web_only_and_guard_rejected_in_chat(self):
        self.assertEqual(self.route("淨零排放是什麼"), "general")
        self.assertEqual(classify_intent("淨零排放是什麼"), "unknown")

    def test_guard_rejection_never_invokes_tutor_agent(self):
        with patch.object(main.tutor_agent, "answer") as tutor_answer:
            reply = main.generate_tutor_answer("CIA Triad 是什麼", user_id="characterization-user")
        tutor_answer.assert_not_called()
        self.assertEqual(reply, route_learning_boundary("CIA Triad 是什麼").response)


class IpasKnowledgePackContractTest(unittest.TestCase):
    """The shared surface the three iPAS packs expose today (input for R4)."""

    PACKS = {
        "ipas_ai_application_planner": (ipas_ai_application_planner, "/api/ipas/answer"),
        "ipas_net_zero_planner": (ipas_net_zero_planner, "/api/ipas/net-zero-planner/answer"),
        "ipas_cybersecurity": (ipas_cybersecurity, "/api/ipas/cybersecurity/answer"),
    }
    COURSE_FIELDS = {"skill_id", "title", "chapter_count", "first_chapter_id"}
    RESULT_FIELDS = {"question_id", "selected_answer", "correct", "correct_answer", "explanation"}

    @staticmethod
    def public_questions(pack):
        if pack is ipas_cybersecurity:
            return [q for chapter in pack.get_chapters() for q in pack.get_questions(chapter["chapter_id"])]
        return pack.get_questions()

    def test_course_info_matches_chapter_index(self):
        for skill_id, (pack, _) in self.PACKS.items():
            with self.subTest(pack=skill_id):
                info = pack.get_course_info()
                self.assertLessEqual(self.COURSE_FIELDS, info.keys())
                self.assertEqual(info["skill_id"], skill_id)
                chapters = pack.get_chapters()
                self.assertEqual(info["chapter_count"], len(chapters))
                self.assertEqual(info["first_chapter_id"], chapters[0]["chapter_id"])
                for chapter in chapters:
                    self.assertEqual(pack.get_chapter(chapter["chapter_id"])["chapter_id"], chapter["chapter_id"])

    def test_every_public_question_hides_answers_and_grades_deterministically(self):
        for skill_id, (pack, _) in self.PACKS.items():
            questions = self.public_questions(pack)
            self.assertTrue(questions, skill_id)
            self.assertEqual(len({q["question_id"] for q in questions}), len(questions), skill_id)
            for question in questions:
                with self.subTest(pack=skill_id, question=question["question_id"]):
                    self.assertEqual(sorted(question["options"]), list("ABCD"))
                    self.assertNotIn("correct_answer", question)
                    self.assertNotIn("explanation", question)
                    probe = pack.submit_answer(question["question_id"], "A")
                    self.assertLessEqual(self.RESULT_FIELDS, probe.keys())
                    correct = probe["correct_answer"]
                    for option in "ABCD":
                        result = pack.submit_answer(question["question_id"], option)
                        self.assertEqual(result["correct"], option == correct)
                        self.assertEqual(result["correct_answer"], correct)

    def test_unknown_question_is_value_error(self):
        for skill_id, (pack, _) in self.PACKS.items():
            with self.subTest(pack=skill_id), self.assertRaises(ValueError):
                pack.submit_answer("NO-SUCH-QUESTION", "A")

    def test_answer_routes_grade_first_question_and_reject_bad_input(self):
        client = main.app.test_client()
        for skill_id, (pack, url) in self.PACKS.items():
            with self.subTest(pack=skill_id):
                question_id = self.public_questions(pack)[0]["question_id"]
                correct = pack.submit_answer(question_id, "A")["correct_answer"]
                response = client.post(url, json={"question_id": question_id, "answer": correct})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json["ok"])
                self.assertTrue(response.json["correct"])
                self.assertEqual(client.post(url, json={"question_id": question_id, "answer": "E"}).status_code, 400)
                self.assertEqual(client.post(url, json={"question_id": "NO-SUCH", "answer": "A"}).status_code, 404)
                self.assertEqual(client.post(url, data="x", content_type="text/plain").status_code, 400)


class FakeGraphResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class MessengerClientTest(unittest.TestCase):
    def test_missing_page_token_sends_nothing(self):
        with patch.dict(os.environ, {"MESSENGER_PAGE_ACCESS_TOKEN": ""}), patch(
            "app.channels.messenger_client.urllib.request.urlopen"
        ) as urlopen:
            self.assertFalse(messenger_client.send_text_message("psid-1", "hello"))
        urlopen.assert_not_called()

    def test_success_posts_recipient_and_text_to_send_api(self):
        opener = Mock(return_value=FakeGraphResponse(200))
        with patch.dict(
            os.environ, {"MESSENGER_PAGE_ACCESS_TOKEN": "page-token", "MESSENGER_API_VERSION": "v20.0"}
        ), patch("app.channels.messenger_client.urllib.request.urlopen", opener):
            self.assertTrue(messenger_client.send_text_message("psid-1", "哈囉"))
        request = opener.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://graph.facebook.com/v20.0/me/messages?"))
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"recipient": {"id": "psid-1"}, "message": {"text": "哈囉"}},
        )
        self.assertEqual(opener.call_args.kwargs["timeout"], 20)

    def test_http_and_network_failures_return_false_without_logging_token(self):
        failures = (
            urllib.error.HTTPError("https://graph.facebook.com", 400, "Bad", {}, io.BytesIO(b"{}")),
            urllib.error.URLError("offline"),
            FakeGraphResponse(500),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), patch.dict(
                os.environ, {"MESSENGER_PAGE_ACCESS_TOKEN": "secret-page-token"}
            ), patch(
                "app.channels.messenger_client.urllib.request.urlopen",
                Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure),
            ), self.assertLogs("messenger_client", level="ERROR") as logs:
                self.assertFalse(messenger_client.send_text_message("psid-1", "hello"))
            self.assertNotIn("secret-page-token", "\n".join(logs.output))


class LineCallbackRouteTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_route_passes_raw_body_and_signature_to_line_handler(self):
        with patch.object(main.handler, "handle") as handle:
            response = self.client.post(
                "/callback", data='{"events":[]}', headers={"X-Line-Signature": "sig-value"}
            )
        self.assertEqual((response.status_code, response.get_data(as_text=True)), (200, "OK"))
        handle.assert_called_once_with('{"events":[]}', "sig-value")

    def test_invalid_signature_is_400(self):
        with patch.object(main.handler, "handle", side_effect=InvalidSignatureError("bad")):
            response = self.client.post("/callback", data="{}", headers={"X-Line-Signature": "bad"})
        self.assertEqual(response.status_code, 400)

    def test_real_handler_rejects_unsigned_request(self):
        self.assertEqual(self.client.post("/callback", data='{"events":[]}').status_code, 400)

    def test_handler_failure_still_acknowledges_webhook(self):
        with patch.object(main.handler, "handle", side_effect=RuntimeError("boom")):
            response = self.client.post("/callback", data="{}", headers={"X-Line-Signature": "sig"})
        self.assertEqual((response.status_code, response.get_data(as_text=True)), (200, "OK"))


if __name__ == "__main__":
    unittest.main()
