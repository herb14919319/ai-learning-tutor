"""R1 regression tests for the shared LLM access boundary.

They were written against the pre-R1 implementation in main.py and must keep
passing unchanged after the extraction: only STATE (the module that owns the
provider clients) moves.
"""

import json
import os
import re
import tempfile
import unittest
from concurrent.futures import TimeoutError
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import main
import runtime_telemetry
from llm import gateway as llm_gateway
from agents.tutor_agent import TutorAgent
from models import resolve_model_provider
from runtime_telemetry import activate_request_context, create_request_context, current_request_outcome

STATE = llm_gateway  # module owning provider clients and telemetry hooks (main.py before R1)


ROOT = Path(__file__).resolve().parents[1]
LEGACY_TELEMETRY_KEYS = [
    "timestamp", "entrypoint", "provider", "model", "status", "error_type", "fallback",
    "fallback_from", "latency_ms", "input_tokens", "output_tokens", "total_tokens",
]
RATE_LIMIT_REPLY = "The model is temporarily busy. Please try again later."


def http_error(code):
    return HTTPError("https://provider.example/v1", code, "provider error", None, BytesIO(b"error"))


_DEFAULT = object()


class FakeClient:
    def __init__(self, name, *, result=_DEFAULT, error=None, usage=None):
        self.provider = name
        self.model = f"{name}-model"
        self.result = f"{name} answer" if result is _DEFAULT else result
        self.error = error
        self.usage = usage
        self.last_usage = "stale"
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        self.last_usage = self.usage
        if self.error is not None:
            raise self.error
        return self.result


class LlmBoundaryTestCase(unittest.TestCase):
    def setUp(self):
        self.recorded = []
        for patcher in (
            patch.object(STATE, "write_runtime_telemetry", side_effect=self.recorded.append),
            # A test must never build a real provider client.
            patch.object(STATE, "create_model_client", side_effect=AssertionError("unexpected client creation")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def ask(self, provider, clients, *, openai=None, entrypoint=None):
        token = main._active_model_provider.set(provider)
        entry_token = main._active_entrypoint.set(entrypoint) if entrypoint else None
        try:
            with patch.object(STATE, "model_clients", clients), patch.object(STATE, "openai_client", openai):
                return main.ask_gpt("system", "user")
        finally:
            if entry_token is not None:
                main._active_entrypoint.reset(entry_token)
            main._active_model_provider.reset(token)


class ProviderSelectionTest(LlmBoundaryTestCase):
    def test_entrypoint_defaults_are_openai(self):
        with patch.dict(os.environ, {}, clear=True):
            for entrypoint in ("web_chat", "line", "messenger", "tutor", "api"):
                with self.subTest(entrypoint=entrypoint):
                    self.assertEqual(resolve_model_provider(entrypoint), "openai")

    def test_entrypoint_env_overrides_and_legacy_alias(self):
        env = {"WEB_CHAT_MODEL_PROVIDER": "gemini", "LINE_MODEL_PROVIDER": "deepseek", "API_MODEL_PROVIDER": "gemini"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_model_provider("web_chat"), "gemini")
            self.assertEqual(resolve_model_provider("line"), "deepseek")
            self.assertEqual(resolve_model_provider("messenger"), "openai")
            self.assertEqual(resolve_model_provider("tutor"), "gemini")  # legacy API_MODEL_PROVIDER
        with patch.dict(os.environ, {"TUTOR_MODEL_PROVIDER": "deepseek", "API_MODEL_PROVIDER": "gemini"}, clear=True):
            self.assertEqual(resolve_model_provider("tutor"), "deepseek")
        with patch.dict(os.environ, {"LINE_MODEL_PROVIDER": "claude"}, clear=True), self.assertRaises(ValueError):
            resolve_model_provider("line")

    def test_generate_tutor_answer_activates_resolved_provider_and_entrypoint(self):
        seen = []
        with patch.dict(os.environ, {"MESSENGER_MODEL_PROVIDER": "deepseek"}), patch.object(
            main, "_generate_tutor_answer",
            side_effect=lambda text, user_id=None: seen.append(
                (main._active_model_provider.get(), main._active_entrypoint.get())) or "ok",
        ):
            self.assertEqual(main.generate_tutor_answer("hi", entrypoint="messenger"), "ok")
            self.assertEqual(main.generate_tutor_answer("hi", entrypoint="line", model_provider="gemini"), "ok")
        self.assertEqual(seen, [("deepseek", "messenger"), ("gemini", "line")])
        self.assertIsNone(main._active_model_provider.get())
        self.assertIsNone(main._active_entrypoint.get())

    def test_without_active_provider_the_configured_default_is_used(self):
        default = FakeClient(STATE.MODEL_PROVIDER)
        with patch.object(STATE, "model_client", default), patch.object(STATE, "openai_client", default), \
             patch.object(STATE, "model_clients", {STATE.MODEL_PROVIDER: default}):
            self.assertEqual(main.ask_gpt("system", "user"), f"{STATE.MODEL_PROVIDER} answer")

    def test_client_lookup_and_caching(self):
        openai = FakeClient("openai")
        default = FakeClient("default")
        created = []

        def fake_create(config):
            created.append(config.provider)
            return FakeClient(config.provider)

        with patch.object(STATE, "openai_client", openai), patch.object(STATE, "model_client", default), \
             patch.object(STATE, "MODEL_PROVIDER", "gemini"), patch.object(STATE, "model_clients", {}) as cache, \
             patch.object(STATE, "create_model_client", side_effect=fake_create):
            self.assertIs(main.get_model_client("OpenAI "), openai)
            self.assertIs(main.get_model_client("gemini"), default)
            deepseek = main.get_model_client("deepseek")
            self.assertIs(main.get_model_client("deepseek"), deepseek)
            self.assertIs(cache["deepseek"], deepseek)
        self.assertEqual(created, ["deepseek"])

    def test_missing_openai_client_is_created_lazily_only_with_api_key(self):
        created = FakeClient("openai")
        with patch.object(STATE, "openai_client", None), patch.object(STATE, "create_model_client", return_value=created):
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                self.assertIsNone(main.get_model_client("openai"))
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}):
                self.assertIs(main.get_model_client("openai"), created)

    def test_unconfigured_provider_raises_runtime_error(self):
        with self.assertRaisesRegex(RuntimeError, "^gemini model API is not configured$"):
            self.ask("gemini", {"gemini": None})


class FallbackOrderTest(LlmBoundaryTestCase):
    def test_retryable_gemini_and_deepseek_errors_fall_back_to_openai_once(self):
        retryable = (http_error(429), http_error(500), http_error(503), URLError("down"), TimeoutError())
        for provider in ("gemini", "deepseek"):
            for error in retryable:
                with self.subTest(provider=provider, error=repr(error)):
                    primary, openai = FakeClient(provider, error=error), FakeClient("openai")
                    with self.assertLogs("main", level="WARNING") as logs:
                        reply = self.ask(provider, {provider: primary}, openai=openai)
                    self.assertEqual(reply, "openai answer")
                    self.assertEqual((len(primary.calls), openai.calls), (1, [("system", "user")]))
                    self.assertIn(f"original_provider={provider} fallback_provider=openai", "\n".join(logs.output))

    def test_non_retryable_errors_raise_without_fallback(self):
        for provider, error in (("gemini", http_error(401)), ("deepseek", http_error(403)),
                                ("deepseek", http_error(400)), ("gemini", ValueError("bad"))):
            with self.subTest(provider=provider, error=repr(error)):
                openai = FakeClient("openai")
                with self.assertRaises(type(error)) as raised:
                    self.ask(provider, {provider: FakeClient(provider, error=error)}, openai=openai)
                self.assertIs(raised.exception, error)
                self.assertEqual(openai.calls, [])

    def test_openai_errors_never_fall_back(self):
        error = http_error(429)
        openai = FakeClient("openai", error=error)
        with self.assertRaises(HTTPError) as raised:
            self.ask("openai", {}, openai=openai)
        self.assertIs(raised.exception, error)
        self.assertEqual(len(openai.calls), 1)

    def test_fallback_unavailable_or_failing_returns_busy_message(self):
        with self.assertLogs("main", level="WARNING") as logs:
            reply = self.ask("gemini", {"gemini": FakeClient("gemini", error=http_error(429))}, openai=None)
        self.assertEqual(reply, RATE_LIMIT_REPLY)
        self.assertEqual(main.MODEL_RATE_LIMIT_FALLBACK_RESPONSE, RATE_LIMIT_REPLY)
        self.assertIn("fallback unavailable", "\n".join(logs.output))

        with self.assertLogs("main", level="ERROR") as logs:
            reply = self.ask("deepseek", {"deepseek": FakeClient("deepseek", error=http_error(503))},
                             openai=FakeClient("openai", error=http_error(500)))
        self.assertEqual(reply, RATE_LIMIT_REPLY)
        self.assertIn("fallback failed", "\n".join(logs.output))

    def test_legacy_gemini_fallback_helper(self):
        with patch.object(STATE, "openai_client", FakeClient("openai")):
            self.assertEqual(main.fallback_from_gemini_rate_limit("s", "u", http_error(429)), "openai answer")


class ResponseAndFailureShapeTest(LlmBoundaryTestCase):
    def test_success_returns_client_output_unmodified(self):
        for result in ("  padded answer \n", "answer"):
            with self.subTest(result=result):
                self.assertEqual(self.ask("openai", {}, openai=FakeClient("openai", result=result)), result)

    def test_empty_or_none_result_is_returned_and_marks_request_error(self):
        for result in ("", "   ", None):
            with self.subTest(result=result):
                context = create_request_context("web_chat", user_scope="anonymous")
                with activate_request_context(context):
                    reply = self.ask("openai", {}, openai=FakeClient("openai", result=result))
                    outcome = current_request_outcome()
                self.assertEqual(reply, result)
                self.assertEqual(outcome, ("error", "provider_invalid_response"))

    def test_error_categories(self):
        cases = {
            "provider_auth_error": (http_error(401), http_error(403)),
            "provider_rate_limit": (http_error(429),),
            "provider_server_error": (http_error(500), http_error(599)),
            "provider_timeout": (TimeoutError(),),
            # HTTPError subclasses URLError: other HTTP statuses fall through to "network".
            "provider_network_error": (URLError("down"), http_error(400), http_error(404)),
            "internal_error": (ValueError("x"), RuntimeError("x")),
        }
        for category, errors in cases.items():
            for error in errors:
                with self.subTest(error=repr(error)):
                    self.assertEqual(main.categorize_provider_error(error), category)
        self.assertTrue(all(main.is_retryable_provider_error(e) for e in (http_error(429), http_error(502), URLError("x"), TimeoutError())))
        self.assertFalse(any(main.is_retryable_provider_error(e) for e in (http_error(401), http_error(404), ValueError("x"))))


class TelemetrySchemaTest(LlmBoundaryTestCase):
    def test_contextless_call_writes_legacy_record_shape(self):
        usage = {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7}
        self.ask("openai", {}, openai=FakeClient("openai", usage=usage), entrypoint="line")
        record = self.recorded[-1]
        self.assertEqual(list(record), LEGACY_TELEMETRY_KEYS)
        self.assertEqual(
            {k: v for k, v in record.items() if k not in ("timestamp", "latency_ms")},
            {"entrypoint": "line", "provider": "openai", "model": "openai-model", "status": "success",
             "error_type": None, "fallback": False, "fallback_from": None,
             "input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
        )
        self.assertIsInstance(record["latency_ms"], int)

    def test_contextless_fallback_records_error_then_fallback_success(self):
        self.ask("gemini", {"gemini": FakeClient("gemini", error=http_error(429), usage={"total_tokens": "x"})},
                 openai=FakeClient("openai"))
        first, second = self.recorded[-2:]
        self.assertEqual(list(first), LEGACY_TELEMETRY_KEYS)
        self.assertEqual((first["entrypoint"], first["provider"], first["status"], first["error_type"]),
                         ("test", "gemini", "error", "HTTPError"))
        self.assertEqual((first["input_tokens"], first["total_tokens"]), (None, None))
        self.assertEqual((second["provider"], second["status"], second["fallback"], second["fallback_from"]),
                         ("openai", "success", True, "gemini"))

    def test_request_context_emits_correlated_provider_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.jsonl"
            context = create_request_context("web_chat", user_scope="anonymous")
            with patch.object(runtime_telemetry, "TELEMETRY_PATH", path), activate_request_context(context):
                self.ask("deepseek", {"deepseek": FakeClient("deepseek", error=http_error(503))},
                         openai=FakeClient("openai", usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}))
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["event"] for e in events],
                         ["provider_attempted", "provider_failed", "provider_fallback", "provider_attempted"])
        self.assertEqual({e["request_id"] for e in events}, {context.request_id})
        self.assertEqual(list(events[0]), list(runtime_telemetry.TELEMETRY_FIELDS))
        attempted, failed, fallback, retried = events
        self.assertEqual((attempted["provider"], attempted["provider_attempt"], attempted["status"],
                          attempted["error_category"], attempted["fallback"]),
                         ("deepseek", 1, "error", "provider_server_error", False))
        self.assertEqual((failed["provider"], failed["provider_attempt"]), ("deepseek", 1))
        self.assertEqual((fallback["status"], fallback["fallback_from"], fallback["fallback_to"]),
                         ("selected", "deepseek", "openai"))
        self.assertEqual((retried["provider"], retried["provider_attempt"], retried["fallback"],
                          retried["fallback_from"], retried["total_tokens"]),
                         ("openai", 2, True, "deepseek", 3))
        self.assertEqual(self.recorded, [])  # correlated path never writes the legacy record

    def test_telemetry_field_contract_is_unchanged(self):
        self.assertEqual(runtime_telemetry.SCHEMA_VERSION, 2)
        self.assertEqual(runtime_telemetry.TELEMETRY_FIELDS, (
            "schema_version", "timestamp", "request_id", "event", "entrypoint", "user_scope", "route",
            "route_reason", "guard_result", "guard_reason", "skill_id", "provider", "provider_attempt",
            "model", "status", "error_category", "error_type", "fallback", "fallback_from", "fallback_to",
            "latency_ms", "question_length", "context_turn_count", "input_tokens", "output_tokens",
            "total_tokens",
        ))


class MainCompatibilityTest(unittest.TestCase):
    def test_main_keeps_llm_names(self):
        for name in ("ask_gpt", "get_model_client", "complete_model_call", "record_model_call_telemetry",
                     "normalize_model_usage", "categorize_provider_error", "is_retryable_provider_error",
                     "fallback_to_openai", "fallback_from_gemini_rate_limit", "MODEL_RATE_LIMIT_FALLBACK_RESPONSE",
                     "MODEL_PROVIDER", "MODEL_NAME", "OPENAI_MODEL", "_active_model_provider", "_active_entrypoint"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(main, name))
        self.assertTrue(callable(main.ask_gpt))

    def test_tutor_agent_is_wired_to_main_ask_gpt(self):
        self.assertIsInstance(main.tutor_agent, TutorAgent)
        self.assertIs(main.tutor_agent._ask_gpt, main.ask_gpt)

    def test_main_names_are_the_llm_boundary(self):
        import llm

        self.assertIs(main.ask_gpt, llm.ask_gpt)
        self.assertIs(main._active_model_provider, llm.active_model_provider)
        self.assertIs(main._active_entrypoint, llm.active_entrypoint)
        self.assertIs(main.categorize_provider_error, llm.categorize_provider_error)
        self.assertEqual(main.MODEL_RATE_LIMIT_FALLBACK_RESPONSE, llm.MODEL_RATE_LIMIT_FALLBACK_RESPONSE)
        self.assertIsNotNone(llm_gateway.MODEL_CONFIG)  # configured by main after load_dotenv()
        self.assertEqual(
            (main.MODEL_CONFIG, main.MODEL_PROVIDER, main.MODEL_NAME, main.OPENAI_MODEL),
            (llm_gateway.MODEL_CONFIG, llm_gateway.MODEL_PROVIDER, llm_gateway.MODEL_NAME, llm_gateway.OPENAI_MODEL),
        )


class DirectClientCallersTest(unittest.TestCase):
    """Callers that bypass ask_gpt keep doing so: fresh env-default client, no fallback, no telemetry."""

    def test_create_default_client_builds_a_fresh_env_default_client_each_call(self):
        created = []
        with patch.object(llm_gateway, "create_model_client",
                          side_effect=lambda *args: created.append(args) or object()):
            first, second = llm_gateway.create_default_client(), llm_gateway.create_default_client()
        self.assertIsNot(first, second)
        self.assertEqual(created, [(), ()])

    def test_migrated_callers_use_default_client_without_shared_policy(self):
        from automation import content_review, source_review
        from skills import hungyi_lee_skill

        client = FakeClient("deepseek", result="raw")
        with patch.object(llm_gateway, "create_model_client", return_value=client), \
             patch.object(llm_gateway, "write_runtime_telemetry") as write, \
             patch.object(hungyi_lee_skill, "_ask_gpt", None):
            self.assertEqual(content_review._existing_model_call("s", "u"), "raw")
            self.assertEqual(source_review._model_call("s", "u"), "raw")
            self.assertEqual(hungyi_lee_skill.ask_gpt("s", "u"), "raw")
        self.assertEqual(client.calls, [("s", "u")] * 3)
        write.assert_not_called()

        failing = FakeClient("deepseek", error=http_error(503))
        with patch.object(llm_gateway, "create_model_client", return_value=failing), \
             self.assertRaises(HTTPError):
            content_review._existing_model_call("s", "u")  # no OpenAI fallback on this path

    def test_unconfigured_callers_keep_their_error_messages(self):
        from automation import content_review, source_review
        from skills import hungyi_lee_skill

        with patch.object(llm_gateway, "create_model_client", return_value=None):
            for call in (content_review._existing_model_call, source_review._model_call):
                with self.subTest(call=call.__module__), self.assertRaisesRegex(RuntimeError, "^Review model is not configured$"):
                    call("s", "u")
            with patch.object(hungyi_lee_skill, "_ask_gpt", None), patch.dict(os.environ, {"MODEL_PROVIDER": "gemini"}), \
                 self.assertRaisesRegex(RuntimeError, "^gemini model API is not configured$"):
                hungyi_lee_skill.ask_gpt("s", "u")


class NoNewDirectClientCreationTest(unittest.TestCase):
    """Model clients may only be constructed inside the LLM boundary and models/."""

    PATTERN = re.compile(r"\b(create_model_client|OpenAIModelClient|GeminiModelClient|DeepSeekModelClient|OpenAI)\(")
    ALLOWED = {"llm/gateway.py", "models/clients.py"}
    EXCLUDED_DIRS = {"venv", ".venv", "tests", ".git", "tmp", "hung-yi-lee-skill", "__pycache__"}

    def test_only_the_boundary_constructs_model_clients(self):
        offenders = []
        for path in ROOT.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if set(path.relative_to(ROOT).parts) & self.EXCLUDED_DIRS or relative in self.ALLOWED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.PATTERN.search(line) and not line.lstrip().startswith(("def ", "#")):
                    offenders.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
