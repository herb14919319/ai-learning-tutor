import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import runtime_telemetry


class RuntimeTelemetryTest(unittest.TestCase):
    dashboard_headers = {"X-Dashboard-Key": "test-dashboard-key"}

    def test_model_call_writes_runtime_telemetry_jsonl(self):
        class FakeOpenAI:
            model = "fake-model"
            last_usage = {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                self.last_usage = {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}
                return "answer"

        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry_path = Path(tmpdir) / "data" / "runtime_telemetry.jsonl"
            provider_token = main._active_model_provider.set("openai")
            entrypoint_token = main._active_entrypoint.set(main.ENTRYPOINT_WEB_CHAT)
            try:
                with patch.object(runtime_telemetry, "TELEMETRY_PATH", telemetry_path), patch.object(
                    main,
                    "openai_client",
                    FakeOpenAI(),
                ):
                    reply = main.ask_gpt("system prompt", "user prompt")
            finally:
                main._active_entrypoint.reset(entrypoint_token)
                main._active_model_provider.reset(provider_token)

            self.assertEqual(reply, "answer")
            record = json.loads(telemetry_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["entrypoint"], "web_chat")
            self.assertEqual(record["provider"], "openai")
            self.assertEqual(record["model"], "fake-model")
            self.assertEqual(record["status"], "success")
            self.assertIsNone(record["error_type"])
            self.assertFalse(record["fallback"])
            self.assertIsNone(record["fallback_from"])
            self.assertEqual(record["input_tokens"], 12)
            self.assertEqual(record["output_tokens"], 8)
            self.assertEqual(record["total_tokens"], 20)
            self.assertIsInstance(record["latency_ms"], int)

    def test_runtime_telemetry_write_failure_is_fail_open(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            blocked_parent = Path(tmpdir) / "not-a-directory"
            blocked_parent.write_text("blocked", encoding="utf-8")
            blocked_path = blocked_parent / "runtime_telemetry.jsonl"

            runtime_telemetry.write_runtime_telemetry(
                {
                    "entrypoint": "web_chat",
                    "provider": "openai",
                    "model": "fake-model",
                    "status": "success",
                },
                path=blocked_path,
            )

    def test_model_call_survives_runtime_telemetry_write_failure(self):
        class FakeOpenAI:
            model = "fake-model"
            last_usage = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                return "answer"

        with tempfile.TemporaryDirectory() as tmpdir:
            blocked_parent = Path(tmpdir) / "not-a-directory"
            blocked_parent.write_text("blocked", encoding="utf-8")
            blocked_path = blocked_parent / "runtime_telemetry.jsonl"
            provider_token = main._active_model_provider.set("openai")
            try:
                with patch.object(runtime_telemetry, "TELEMETRY_PATH", blocked_path), patch.object(
                    main,
                    "openai_client",
                    FakeOpenAI(),
                ):
                    reply = main.ask_gpt("system prompt", "user prompt")
            finally:
                main._active_model_provider.reset(provider_token)

        self.assertEqual(reply, "answer")

    def test_runtime_telemetry_api_denies_access_when_dashboard_key_is_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            response = main.app.test_client().get("/api/runtime/telemetry?month=2026-07")

        self.assertIn(response.status_code, (401, 403))

    def test_dashboard_route_denies_access_when_dashboard_key_is_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            response = main.app.test_client().get("/dashboard?month=2026-07")

        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn("Runtime Observability", response.get_data(as_text=True))

    def test_observability_route_denies_access_when_dashboard_key_is_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            response = main.app.test_client().get("/observability?month=2026-07")

        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn("Runtime Observability", response.get_data(as_text=True))

    def test_dashboard_route_denies_access_when_key_is_missing_or_wrong(self):
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "test-dashboard-key"}, clear=True):
            missing_response = main.app.test_client().get("/dashboard?month=2026-07")
            wrong_response = main.app.test_client().get(
                "/dashboard?month=2026-07",
                headers={"X-Dashboard-Key": "wrong-key"},
            )

        self.assertIn(missing_response.status_code, (401, 403))
        self.assertIn(wrong_response.status_code, (401, 403))

    def test_runtime_telemetry_api_denies_access_when_key_is_missing_or_wrong(self):
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "test-dashboard-key"}, clear=True):
            missing_response = main.app.test_client().get("/api/runtime/telemetry?month=2026-07")
            wrong_response = main.app.test_client().get(
                "/api/runtime/telemetry?month=2026-07",
                headers={"X-Dashboard-Key": "wrong-key"},
            )

        self.assertIn(missing_response.status_code, (401, 403))
        self.assertIn(wrong_response.status_code, (401, 403))

    def test_runtime_telemetry_api_returns_empty_summary_without_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry_path = Path(tmpdir) / "missing" / "runtime_telemetry.jsonl"
            with patch.dict(os.environ, {"DASHBOARD_API_KEY": "test-dashboard-key"}, clear=True), patch.object(
                runtime_telemetry,
                "TELEMETRY_PATH",
                telemetry_path,
            ):
                response = main.app.test_client().get(
                    "/api/runtime/telemetry?month=2026-07",
                    headers=self.dashboard_headers,
                )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["month"], "2026-07")
        self.assertEqual(data["total_requests"], 0)
        self.assertEqual(data["success"], 0)
        self.assertEqual(data["error"], 0)
        self.assertEqual(data["total_tokens"], 0)
        self.assertEqual(data["fallback_count"], 0)
        self.assertEqual(data["by_entrypoint"], [])
        self.assertEqual(data["by_provider"], [])
        self.assertEqual(data["recent_requests"], [])

    def test_runtime_telemetry_api_aggregates_by_entrypoint_and_provider(self):
        records = [
            {
                "timestamp": "2026-07-01T00:00:00+00:00",
                "entrypoint": "web_chat",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "status": "success",
                "error_type": None,
                "fallback": False,
                "fallback_from": None,
                "latency_ms": 100,
                "input_tokens": 10,
                "output_tokens": 15,
                "total_tokens": 25,
            },
            {
                "timestamp": "2026-07-02T00:00:00+00:00",
                "entrypoint": "api",
                "provider": "gemini",
                "model": "gemini-2.0-flash",
                "status": "error",
                "error_type": "HTTPError",
                "fallback": False,
                "fallback_from": None,
                "latency_ms": 50,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            },
            {
                "timestamp": "2026-07-02T00:00:01+00:00",
                "entrypoint": "api",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "status": "success",
                "error_type": None,
                "fallback": True,
                "fallback_from": "gemini",
                "latency_ms": 80,
                "input_tokens": 4,
                "output_tokens": 6,
                "total_tokens": 10,
            },
            {
                "timestamp": "2026-06-30T00:00:00+00:00",
                "entrypoint": "line",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "status": "success",
                "error_type": None,
                "fallback": False,
                "fallback_from": None,
                "latency_ms": 90,
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry_path = Path(tmpdir) / "runtime_telemetry.jsonl"
            telemetry_path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"DASHBOARD_API_KEY": "test-dashboard-key"}, clear=True), patch.object(
                runtime_telemetry,
                "TELEMETRY_PATH",
                telemetry_path,
            ):
                response = main.app.test_client().get(
                    "/api/runtime/telemetry?month=2026-07",
                    headers=self.dashboard_headers,
                )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["total_requests"], 3)
        self.assertEqual(data["success"], 2)
        self.assertEqual(data["error"], 1)
        self.assertEqual(data["total_tokens"], 35)
        self.assertEqual(data["fallback_count"], 1)
        self.assertEqual(
            data["by_entrypoint"],
            [
                {"entrypoint": "api", "requests": 2, "tokens": 10},
                {"entrypoint": "web_chat", "requests": 1, "tokens": 25},
            ],
        )
        self.assertEqual(
            data["by_provider"],
            [
                {"provider": "gemini", "requests": 1, "tokens": 0, "errors": 1},
                {"provider": "openai", "requests": 2, "tokens": 35, "errors": 0},
            ],
        )
        self.assertEqual(len(data["recent_requests"]), 3)
        self.assertEqual(data["recent_requests"][0]["timestamp"], "2026-07-02T00:00:01+00:00")

    def test_dashboard_route_returns_200(self):
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "test-dashboard-key"}, clear=True):
            response = main.app.test_client().get("/dashboard?month=2026-07", headers=self.dashboard_headers)

        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Runtime Observability", body)
        self.assertIn("/api/runtime/telemetry", body)

    def test_observability_route_returns_200(self):
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "test-dashboard-key"}, clear=True):
            response = main.app.test_client().get("/observability?month=2026-07", headers=self.dashboard_headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Runtime Observability", response.get_data(as_text=True))

    def test_observability_key_env_can_authorize_dashboard_routes(self):
        with patch.dict(os.environ, {"OBSERVABILITY_API_KEY": "test-dashboard-key"}, clear=True):
            response = main.app.test_client().get("/observability?month=2026-07", headers=self.dashboard_headers)

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
