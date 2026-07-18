import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import main
import runtime_telemetry
from agents.tutor_agent import TutorAgent


def read_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class RequestCorrelationTelemetryTest(unittest.TestCase):
    def setUp(self):
        main.tutor_api_rate_limits.clear()
        main.tutor_api_daily_quotas.clear()
        main.fa_web_rate_limits.clear()

    def tearDown(self):
        main.tutor_api_rate_limits.clear()
        main.tutor_api_daily_quotas.clear()
        main.fa_web_rate_limits.clear()

    def test_each_request_has_one_unique_id_across_the_lifecycle(self):
        allowed = SimpleNamespace(allowed=True, intent="learning", response=None)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.object(
                main, "route_learning_boundary", return_value=allowed
            ), patch.object(main.tutor_agent, "answer", return_value="answer"):
                main.generate_tutor_answer("What is RAG?", entrypoint=main.ENTRYPOINT_WEB_CHAT)
                main.generate_tutor_answer("What is MCP?", entrypoint=main.ENTRYPOINT_WEB_CHAT)

            records = read_records(path)

        request_ids = {record["request_id"] for record in records}
        self.assertEqual(len(request_ids), 2)
        for request_id in request_ids:
            lifecycle = [record for record in records if record["request_id"] == request_id]
            self.assertEqual(lifecycle[0]["event"], "request_received")
            self.assertEqual(lifecycle[-1]["event"], "request_completed")
            self.assertTrue(all(record["schema_version"] == 2 for record in lifecycle))

    def test_all_tutor_entrypoints_emit_unique_terminal_lifecycles(self):
        allowed = SimpleNamespace(allowed=True, intent="learning", response=None)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.object(
                main, "route_learning_boundary", return_value=allowed
            ), patch.object(main.tutor_agent, "answer", return_value="answer"), patch.dict(
                os.environ, {"AI_TUTOR_API_KEY": "test-key"}
            ):
                main.generate_tutor_reply("line:user", "What is RAG?")
                main.generate_messenger_tutor_reply("messenger:user", "What is RAG?")
                client = main.app.test_client()
                client.post("/web-chat", json={"message": "What is RAG?"})
                agent_response = client.post(
                    "/api/agent/ask",
                    json={"question": "What is RAG?"},
                    headers={"X-API-Key": "test-key"},
                )
                client.post(
                    "/api/tutor/ask",
                    json={"question": "What is RAG?"},
                    headers={"X-API-Key": "test-key"},
                )
                client.get(
                    "/test?question=What+is+RAG%3F",
                    headers={"X-API-Key": "test-key"},
                )
            records = read_records(path)

        terminal_records = [
            record
            for record in records
            if record["event"] in {"request_completed", "request_failed"}
        ]
        self.assertEqual(
            {record["entrypoint"] for record in terminal_records},
            {"line", "messenger", "web_chat", "api_agent", "api_tutor", "test"},
        )
        self.assertEqual(len({record["request_id"] for record in terminal_records}), 6)
        self.assertEqual(agent_response.get_json()["call_id"], next(
            record["request_id"]
            for record in terminal_records
            if record["entrypoint"] == "api_agent"
        ))

    def test_guard_rejection_records_stable_reason_and_request_result(self):
        rejected = SimpleNamespace(allowed=False, intent="out_of_scope", response="rejected")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.object(
                main, "route_learning_boundary", return_value=rejected
            ), patch.object(main.tutor_agent, "answer") as answer:
                reply = main.generate_tutor_answer("Tell me a joke")

            records = read_records(path)

        self.assertEqual(reply, "rejected")
        answer.assert_not_called()
        guard = next(record for record in records if record["event"] == "guard_evaluated")
        terminal = records[-1]
        self.assertEqual(guard["guard_result"], "rejected")
        self.assertEqual(guard["guard_reason"], "out_of_scope")
        self.assertEqual(guard["error_category"], "guard_rejected")
        self.assertEqual(terminal["event"], "request_completed")
        self.assertEqual(terminal["status"], "rejected")

    def test_retryable_failure_and_fallback_share_request_id_and_count_once(self):
        server_error = HTTPError(
            url="https://api.deepseek.com/chat/completions",
            code=503,
            msg="provider error",
            hdrs=None,
            fp=BytesIO(b"provider response must not be logged"),
        )

        class FailingDeepSeek:
            model = "deepseek-chat"

            def complete(self, system_prompt, user_prompt):
                raise server_error

        class AvailableOpenAI:
            model = "gpt-test"
            last_usage = {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}

            def complete(self, system_prompt, user_prompt):
                return "fallback answer"

        allowed = SimpleNamespace(allowed=True, intent="learning", response=None)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.object(
                main, "route_learning_boundary", return_value=allowed
            ), patch.object(
                main.tutor_agent,
                "answer",
                side_effect=lambda message, user_id=None: main.ask_gpt("system", message),
            ), patch.object(main, "model_clients", {"deepseek": FailingDeepSeek()}), patch.object(
                main, "openai_client", AvailableOpenAI()
            ):
                reply = main.generate_tutor_answer(
                    "What is RAG?",
                    entrypoint=main.ENTRYPOINT_API,
                    model_provider="deepseek",
                )
                records = read_records(path)
                summary = runtime_telemetry.aggregate_runtime_telemetry(
                    records[0]["timestamp"][:7],
                    path,
                )

        self.assertEqual(reply, "fallback answer")
        self.assertEqual(len({record["request_id"] for record in records}), 1)
        attempts = [record for record in records if record["event"] == "provider_attempted"]
        self.assertEqual([record["provider_attempt"] for record in attempts], [1, 2])
        self.assertEqual([record["provider"] for record in attempts], ["deepseek", "openai"])
        fallback = next(record for record in records if record["event"] == "provider_fallback")
        self.assertEqual((fallback["fallback_from"], fallback["fallback_to"]), ("deepseek", "openai"))
        failed = next(record for record in records if record["event"] == "provider_failed")
        self.assertEqual(failed["error_category"], "provider_server_error")
        self.assertEqual(summary["total_requests"], 1)
        self.assertEqual(summary["provider_attempts"], 2)
        self.assertEqual(summary["fallback_count"], 1)
        self.assertEqual(summary["success"], 1)

    def test_provider_authentication_failure_does_not_fallback(self):
        auth_error = HTTPError(
            url="https://api.deepseek.com/chat/completions",
            code=401,
            msg="unauthorized",
            hdrs=None,
            fp=BytesIO(),
        )

        class UnauthorizedDeepSeek:
            model = "deepseek-chat"

            def complete(self, system_prompt, user_prompt):
                raise auth_error

        allowed = SimpleNamespace(allowed=True, intent="learning", response=None)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.object(
                main, "route_learning_boundary", return_value=allowed
            ), patch.object(
                main.tutor_agent,
                "answer",
                side_effect=lambda message, user_id=None: main.ask_gpt("system", message),
            ), patch.object(main, "model_clients", {"deepseek": UnauthorizedDeepSeek()}), patch.object(
                main, "openai_client"
            ) as openai:
                with self.assertRaises(HTTPError):
                    main.generate_tutor_answer(
                        "What is RAG?",
                        model_provider="deepseek",
                    )
                records = read_records(path)

        openai.assert_not_called()
        self.assertFalse(any(record["event"] == "provider_fallback" for record in records))
        failed = next(record for record in records if record["event"] == "provider_failed")
        self.assertEqual(failed["error_category"], "provider_auth_error")
        self.assertEqual(records[-1]["event"], "request_failed")

    def test_skill_route_records_selected_skill_id(self):
        class FakeRuntime:
            context = {}

            def configure(self, ask_gpt):
                return None

            def normalize_request(self, message):
                return SimpleNamespace(text=message)

            def route(self, request):
                return {"skill": "quiz", "reason": "matched_quiz"}

            def get_skill(self, skill_name):
                return SimpleNamespace(answer=lambda request, context: "quiz answer")

        agent = TutorAgent(lambda system, user: "general", skill_runtime=FakeRuntime())
        allowed = SimpleNamespace(allowed=True, intent="learning", response=None)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.object(
                main, "route_learning_boundary", return_value=allowed
            ), patch.object(main, "tutor_agent", agent):
                reply = main.generate_tutor_answer("Start a quiz")
            records = read_records(path)

        self.assertEqual(reply, "quiz answer")
        route = next(record for record in records if record["event"] == "route_selected")
        skill = next(record for record in records if record["event"] == "skill_selected")
        self.assertEqual(route["route"], "quiz")
        self.assertEqual(route["route_reason"], "matched_quiz")
        self.assertEqual(skill["skill_id"], "quiz")

    def test_early_api_validation_is_terminal_and_call_id_is_correlated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), patch.dict(
                os.environ, {"AI_TUTOR_API_KEY": "test-key"}
            ):
                response = main.app.test_client().post(
                    "/api/agent/ask",
                    json={"caller": "test"},
                    headers={"X-API-Key": "test-key"},
                )
                records = read_records(path)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["call_id"], records[0]["request_id"])
        self.assertEqual(records[-1]["event"], "request_failed")
        self.assertEqual(records[-1]["error_category"], "validation_error")

    def test_telemetry_allowlist_excludes_sensitive_values(self):
        secret_values = [
            "raw-user-123",
            "api-key-secret",
            "messenger-signature",
            "raw prompt content",
            "raw answer content",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.jsonl"
            context = runtime_telemetry.create_request_context(
                "web_chat",
                user_scope="anonymous",
                question_length=18,
            )
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path):
                runtime_telemetry.write_runtime_telemetry(
                    {
                        "schema_version": 2,
                        "request_id": context.request_id,
                        "event": "request_received",
                        "entrypoint": "web_chat",
                        "status": "received",
                        "user_id": secret_values[0],
                        "api_key": secret_values[1],
                        "signature": secret_values[2],
                        "prompt": secret_values[3],
                        "answer": secret_values[4],
                    }
                )
            serialized = path.read_text(encoding="utf-8")

        for value in secret_values:
            self.assertNotIn(value, serialized)


if __name__ == "__main__":
    unittest.main()
