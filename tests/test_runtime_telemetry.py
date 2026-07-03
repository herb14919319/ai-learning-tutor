import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import runtime_telemetry


class RuntimeTelemetryTest(unittest.TestCase):
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

    def test_runtime_telemetry_api_returns_empty_summary_without_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry_path = Path(tmpdir) / "missing" / "runtime_telemetry.jsonl"
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", telemetry_path):
                response = main.app.test_client().get("/api/runtime/telemetry?month=2026-07")

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
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", telemetry_path):
                response = main.app.test_client().get("/api/runtime/telemetry?month=2026-07")

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
        response = main.app.test_client().get("/dashboard?month=2026-07")

        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Runtime Observability", body)
        self.assertIn("/api/runtime/telemetry", body)

    def test_observability_route_returns_200(self):
        response = main.app.test_client().get("/observability?month=2026-07")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Runtime Observability", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
