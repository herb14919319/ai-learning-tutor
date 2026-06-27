import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch

import main
from menu_router import is_menu_command
from agents.ai_acronyms import build_ai_acronym_disambiguation_prompt
from agents.router import route
from agents.tutor_agent import TutorAgent
from skills.registry import get_skill_metadata, list_skills
from skills.runtime import SkillCatalog, SkillManifest, SkillRuntime


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class TimeoutFuture:
    def result(self, timeout=None):
        raise main.TimeoutError()


class TimeoutExecutor:
    def submit(self, fn, *args, **kwargs):
        return TimeoutFuture()


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))


def fake_line_event(
    *,
    text: str = "請解釋 Transformer",
    reply_token: str = "reply-token-1",
    event_id: str | None = "event-1",
    message_id: str | None = "message-1",
    user_id: str = "user-1",
):
    return SimpleNamespace(
        reply_token=reply_token,
        webhook_event_id=event_id,
        source=SimpleNamespace(user_id=user_id),
        message=SimpleNamespace(id=message_id, text=text),
    )


class FakeSkill:
    @staticmethod
    def answer(user_message: str) -> str:
        return f"skill:{user_message}"


class BrokenSkill:
    @staticmethod
    def answer(user_message: str) -> str:
        raise RuntimeError("boom")


class TutorAgentTest(unittest.TestCase):
    def test_list_skills_includes_hungyi_lee(self):
        self.assertIn("hungyi_lee", [metadata.name for metadata in list_skills()])

    def test_hungyi_lee_metadata_can_be_read(self):
        metadata = get_skill_metadata("hungyi_lee")

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.name, "hungyi_lee")
        self.assertTrue(metadata.enabled)
        self.assertIn("AI", metadata.domain)
        self.assertIn("AI", metadata.domains)
        self.assertIn("Transformer", metadata.keywords)
        self.assertIn("answer_ai_learning_question", metadata.capabilities)
        self.assertEqual(metadata.entrypoint, "skills.hungyi_lee_skill")

    def test_ai_question_routes_to_hungyi_lee(self):
        self.assertEqual(route("什麼是 Transformer？")["skill"], "hungyi_lee")
        self.assertEqual(route("RAG 跟 fine-tune 差在哪？")["skill"], "hungyi_lee")
        self.assertEqual(route("我想學生成式AI")["skill"], "hungyi_lee")

    def test_non_ai_question_routes_to_general(self):
        self.assertEqual(route("今天晚餐適合吃什麼？")["skill"], "general")
        self.assertEqual(route("Taiwan 旅遊三天怎麼排？")["skill"], "general")

    def test_agent_calls_selected_skill(self):
        with patch("agents.tutor_agent.configure_skills"), patch(
            "agents.tutor_agent.get_skill", return_value=FakeSkill
        ):
            agent = TutorAgent(lambda system, user: "general")

            self.assertEqual(agent.answer("什麼是 LLM？"), "skill:什麼是 LLM？")

    def test_skill_exception_falls_back_to_general_answer(self):
        def fake_ask_gpt(system_prompt: str, user_prompt: str) -> str:
            return f"general:{user_prompt}"

        with patch("agents.tutor_agent.configure_skills"), patch(
            "agents.tutor_agent.get_skill", return_value=BrokenSkill
        ):
            agent = TutorAgent(fake_ask_gpt)

            with self.assertLogs("agents.tutor_agent", level="ERROR") as logs:
                self.assertTrue(agent.answer("什麼是 LLM？").startswith("general:"))

        self.assertTrue(any("Skill failed: hungyi_lee" in message for message in logs.output))

    def test_disabled_skill_fails_open_to_general_answer(self):
        catalog = SkillCatalog(
            (
                SkillManifest(
                    name="disabled_ai",
                    display_name="Disabled AI",
                    description="Disabled test skill",
                    domains=("AI",),
                    keywords=("LLM",),
                    capabilities=("answer",),
                    entrypoint="tests.test_agent",
                    priority=100,
                    enabled=False,
                ),
            )
        )
        runtime = SkillRuntime(catalog)
        agent = TutorAgent(lambda system, user: f"general:{user}", skill_runtime=runtime)

        self.assertTrue(agent.answer("What is an LLM?").startswith("general:"))

    def test_ai_acronym_question_routes_to_hungyi_lee(self):
        self.assertEqual(route("MCP 是什麼？")["skill"], "hungyi_lee")
        self.assertEqual(route("MCP 跟 RAG 有什麼關係？")["skill"], "hungyi_lee")

    def test_mcp_defaults_to_model_context_protocol_prompt(self):
        hint = build_ai_acronym_disambiguation_prompt("MCP 是什麼？")

        self.assertIn("Model Context Protocol", hint)
        self.assertIn("在 AI Agent 領域中", hint)
        self.assertIn("不要把 MCP 優先解釋為 Microsoft Certified Professional", hint)

    def test_mcp_with_rag_defaults_to_model_context_protocol_prompt(self):
        hint = build_ai_acronym_disambiguation_prompt("MCP 跟 RAG 有什麼關係？")

        self.assertIn("Model Context Protocol", hint)
        self.assertIn("AI Agent", hint)

    def test_microsoft_mcp_certification_prompt(self):
        hint = build_ai_acronym_disambiguation_prompt("微軟 MCP 證照是什麼？")

        self.assertIn("Microsoft Certified Professional", hint)
        self.assertIn("微軟認證專家", hint)

    def test_microsoft_certified_professional_prompt(self):
        hint = build_ai_acronym_disambiguation_prompt("Microsoft Certified Professional 是什麼？")

        self.assertIn("Microsoft Certified Professional", hint)
        self.assertIn("微軟認證專家", hint)

    def test_agent_injects_mcp_disambiguation_into_general_prompt(self):
        prompts = []

        def fake_ask_gpt(system_prompt: str, user_prompt: str) -> str:
            prompts.append((system_prompt, user_prompt))
            return "在 AI Agent 領域中，MCP 通常指 Model Context Protocol。"

        runtime = SkillRuntime(SkillCatalog(()))
        agent = TutorAgent(fake_ask_gpt, skill_runtime=runtime)

        answer = agent.answer("MCP 是什麼？")

        self.assertIn("Model Context Protocol", answer)
        self.assertIn("Model Context Protocol", prompts[0][0])
        self.assertIn("不要把 MCP 優先解釋為 Microsoft Certified Professional", prompts[0][0])


class AgentAskApiTest(unittest.TestCase):
    def test_successful_agent_ask_returns_metadata(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="RAG retrieves context before generation."
        ) as answer:
            response = main.app.test_client().post(
                "/api/agent/ask",
                json={"question": "What is RAG?", "caller": "baeko", "user_id": "amos"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["answer"], "RAG retrieves context before generation.")
        self.assertEqual(data["source_agent"], "ai_learning_tutor")
        self.assertEqual(data["handled_by"], "answer_question")
        self.assertEqual(data["capability"], "answer_question")
        self.assertEqual(data["caller"], "baeko")
        self.assertTrue(data["call_id"])
        self.assertEqual(data["confidence"], "medium")
        answer.assert_called_once_with("What is RAG?", user_id="amos")

    def test_capability_agent_ask_returns_same_answer_flow(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="RAG retrieves context before generation."
        ) as answer:
            response = main.app.test_client().post(
                "/api/agent/ask",
                json={
                    "task": "answer_question",
                    "caller": "baeko",
                    "user_id": "amos",
                    "input": {"question": "What is RAG?"},
                    "context": {},
                    "memory": "ignored",
                    "messages": [{"role": "user", "content": "ignored"}],
                },
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["answer"], "RAG retrieves context before generation.")
        self.assertEqual(data["handled_by"], "answer_question")
        self.assertEqual(data["capability"], "answer_question")
        self.assertEqual(data["caller"], "baeko")
        answer.assert_called_once_with("What is RAG?", user_id="amos")

    def test_old_and_capability_formats_return_same_metadata_except_call_id(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="same answer"
        ):
            client = main.app.test_client()
            old_response = client.post(
                "/api/agent/ask",
                json={"question": "What is RAG?", "caller": "baeko", "user_id": "amos"},
            )
            new_response = client.post(
                "/api/agent/ask",
                json={
                    "task": "answer_question",
                    "caller": "baeko",
                    "user_id": "amos",
                    "input": {"question": "What is RAG?"},
                    "context": {},
                },
            )

        old_data = old_response.get_json()
        new_data = new_response.get_json()
        old_data.pop("call_id")
        new_data.pop("call_id")
        self.assertEqual(old_response.status_code, 200)
        self.assertEqual(new_response.status_code, 200)
        self.assertEqual(old_data, new_data)

    def test_dispatcher_routes_answer_question_to_tutor_answer(self):
        with patch.object(main, "generate_tutor_answer", return_value="answer") as generate:
            handled_by, answer = main.dispatch_agent_capability(
                "answer_question", question="What is RAG?", user_id="amos"
            )

        self.assertEqual(handled_by, "answer_question")
        self.assertEqual(answer, "answer")
        generate.assert_called_once_with("What is RAG?", user_id="amos")

    def test_unsupported_task_returns_400(self):
        with patch.object(main, "generate_tutor_answer") as generate:
            response = main.app.test_client().post(
                "/api/agent/ask",
                json={
                    "task": "quiz",
                    "caller": "baeko",
                    "input": {"question": "What is RAG?"},
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "unsupported_task"})
        generate.assert_not_called()

    def test_missing_question_returns_400(self):
        response = main.app.test_client().post("/api/agent/ask", json={"caller": "baeko"})

        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "missing_question")
        self.assertEqual(data["source_agent"], "ai_learning_tutor")
        self.assertTrue(data["call_id"])

    def test_caller_defaults_to_unknown(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="answer"
        ):
            response = main.app.test_client().post(
                "/api/agent/ask",
                json={"question": "What is an embedding?"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["caller"], "unknown")

    def test_agent_ask_does_not_trigger_line_reply_or_push(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="answer"
        ), patch.object(main, "reply_text") as reply_text, patch.object(main, "push_text") as push_text:
            response = main.app.test_client().post(
                "/api/agent/ask",
                json={"question": "What is RAG?", "caller": "baeko"},
            )

        self.assertEqual(response.status_code, 200)
        reply_text.assert_not_called()
        push_text.assert_not_called()

    def test_agent_ask_logs_call_id_and_caller(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="answer"
        ), self.assertLogs("main", level="INFO") as logs:
            response = main.app.test_client().post(
                "/api/agent/ask",
                json={"question": "What is RAG?", "caller": "baeko"},
            )

        call_id = response.get_json()["call_id"]
        log_text = "\n".join(logs.output)
        self.assertIn(f"call_id={call_id}", log_text)
        self.assertIn("caller=baeko", log_text)
        self.assertIn("task=answer_question", log_text)
        self.assertIn("handled_by=answer_question", log_text)
        self.assertIn("duration_ms=", log_text)
        self.assertIn("[AGENT_API] received", log_text)
        self.assertIn("[AGENT_API] dispatch capability=answer_question", log_text)
        self.assertIn("[AGENT_API] answered", log_text)

    def test_internal_error_returns_500_without_exception_details(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", side_effect=RuntimeError("secret failure")
        ):
            response = main.app.test_client().post(
                "/api/agent/ask",
                json={"question": "What is RAG?", "caller": "baeko"},
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "internal_error")
        self.assertEqual(data["source_agent"], "ai_learning_tutor")
        self.assertTrue(data["call_id"])
        self.assertNotIn("secret failure", str(data))


class TutorAskApiTest(unittest.TestCase):
    def setUp(self):
        main.tutor_api_rate_limits.clear()
        main.tutor_api_daily_quotas.clear()

    def tearDown(self):
        main.tutor_api_rate_limits.clear()
        main.tutor_api_daily_quotas.clear()

    def post_tutor_ask(self, *, json=None, data=None, content_type=None, api_key: str | None = "test-key"):
        headers = {}
        if api_key is not None:
            headers["X-API-Key"] = api_key
        return main.app.test_client().post(
            "/api/tutor/ask",
            json=json,
            data=data,
            content_type=content_type,
            headers=headers,
        )

    def test_valid_api_key_allows_request(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "generate_tutor_answer", return_value="answer"
        ) as generate:
            response = self.post_tutor_ask(json={"question": "What is MCP?"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        generate.assert_called_once_with("What is MCP?", user_id=None)

    def test_invalid_api_key_returns_401(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "generate_tutor_answer"
        ) as generate:
            response = self.post_tutor_ask(json={"question": "What is MCP?"}, api_key="wrong-key")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"ok": False, "error": "unauthorized"})
        generate.assert_not_called()
        self.assertEqual(main.tutor_api_daily_quotas, {})

    def test_missing_api_key_header_returns_401(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "generate_tutor_answer"
        ) as generate:
            response = self.post_tutor_ask(json={"question": "What is MCP?"}, api_key=None)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"ok": False, "error": "unauthorized"})
        generate.assert_not_called()

    def test_missing_api_key_env_returns_500(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(main, "generate_tutor_answer") as generate:
            with self.assertLogs("main", level="ERROR") as logs:
                response = self.post_tutor_ask(json={"question": "What is MCP?"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"ok": False, "error": "server_not_configured"})
        self.assertTrue(any("AI_TUTOR_API_KEY is not configured" in message for message in logs.output))
        generate.assert_not_called()

    def test_successful_answer_returns_external_api_shape(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "generate_tutor_answer", return_value="MCP usually means Model Context Protocol."
        ) as generate:
            response = self.post_tutor_ask(
                json={
                    "question": "What is MCP?",
                    "user_id": "baeko",
                    "source": "baeko_callout",
                    "metadata": {
                        "caller": "baeko",
                        "required_capability": "knowledge",
                        "future_field": {"nested": True},
                    },
                }
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "ok": True,
                "answer": "MCP usually means Model Context Protocol.",
                "source": "ai-learning-tutor",
            },
        )
        generate.assert_called_once_with("What is MCP?", user_id="baeko")

    def test_oversized_payload_returns_413(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "dispatch_tutor_api_request"
        ) as dispatch:
            response = self.post_tutor_ask(
                data="x" * (main.TUTOR_API_MAX_CONTENT_LENGTH + 1),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json(), {"ok": False, "error": "Payload too large"})
        dispatch.assert_not_called()

    def test_invalid_question_type_returns_400(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "dispatch_tutor_api_request"
        ) as dispatch:
            response = self.post_tutor_ask(json={"question": 123})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "Invalid question"})
        dispatch.assert_not_called()

    def test_metadata_is_preserved_for_internal_dispatch(self):
        metadata = {
            "caller": "baeko",
            "required_capability": "knowledge",
            "future_field": {"nested": True},
        }
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "dispatch_tutor_api_request", return_value="answer"
        ) as dispatch:
            response = self.post_tutor_ask(
                json={
                    "question": "What is MCP?",
                    "user_id": "baeko",
                    "source": "baeko_callout",
                    "metadata": metadata,
                }
            )

        self.assertEqual(response.status_code, 200)
        dispatch.assert_called_once_with(
            {
                "question": "What is MCP?",
                "user_id": "baeko",
                "source": "baeko_callout",
                "metadata": metadata,
            }
        )

    def test_empty_question_returns_400(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "generate_tutor_answer"
        ) as generate:
            response = self.post_tutor_ask(json={"question": "   ", "metadata": {"caller": "baeko"}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "Invalid question"})
        generate.assert_not_called()

    def test_question_too_long_returns_400(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "dispatch_tutor_api_request"
        ) as dispatch:
            response = self.post_tutor_ask(json={"question": "a" * (main.TUTOR_API_MAX_QUESTION_LENGTH + 1)})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "Invalid question"})
        dispatch.assert_not_called()

    def test_rate_limit_exceeded_returns_429(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "TUTOR_API_RATE_LIMIT_REQUESTS", 1
        ), patch.object(main, "dispatch_tutor_api_request", return_value="answer") as dispatch:
            first_response = self.post_tutor_ask(json={"question": "What is MCP?"})
            second_response = self.post_tutor_ask(json={"question": "What is MCP?"})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)
        self.assertEqual(second_response.get_json(), {"ok": False, "error": "Rate limit exceeded"})
        dispatch.assert_called_once()

    def test_daily_quota_exceeded_returns_403(self):
        main.tutor_api_daily_quotas["test-key"] = {
            "date": main.date.today().isoformat(),
            "count": main.TUTOR_API_DAILY_QUOTA,
        }
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "dispatch_tutor_api_request"
        ) as dispatch:
            response = self.post_tutor_ask(json={"question": "What is MCP?"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"ok": False, "error": "Daily quota exceeded"})
        dispatch.assert_not_called()

    def test_daily_quota_resets_when_date_changes(self):
        main.tutor_api_daily_quotas["test-key"] = {"date": "1900-01-01", "count": main.TUTOR_API_DAILY_QUOTA}
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "dispatch_tutor_api_request", return_value="answer"
        ):
            response = self.post_tutor_ask(json={"question": "What is MCP?"})

        quota = main.tutor_api_daily_quotas["test-key"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(quota["date"], main.date.today().isoformat())
        self.assertEqual(quota["count"], 1)

    def test_audit_logging_for_authenticated_request(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "dispatch_tutor_api_request", return_value="answer"
        ), self.assertLogs("main", level="INFO") as logs:
            response = self.post_tutor_ask(
                json={"question": "What is MCP?", "source": "baeko_callout", "user_id": "baeko"},
            )

        log_text = "\n".join(logs.output)
        self.assertEqual(response.status_code, 200)
        self.assertIn("[TUTOR_API_AUDIT]", log_text)
        self.assertIn("client_ip=127.0.0.1", log_text)
        self.assertIn("source=baeko_callout", log_text)
        self.assertIn("user_id=baeko", log_text)
        self.assertIn("question_length=12", log_text)
        self.assertIn("status=200", log_text)
        self.assertIn("duration_ms=", log_text)
        self.assertNotIn("test-key", log_text)
        self.assertNotIn("answer", log_text)

    def test_internal_exception_returns_500_without_details(self):
        with patch.dict(os.environ, {"AI_TUTOR_API_KEY": "test-key"}), patch.object(
            main, "generate_tutor_answer", side_effect=RuntimeError("secret failure")
        ):
            response = self.post_tutor_ask(
                json={
                    "question": "What is MCP?",
                    "source": "baeko_callout",
                    "metadata": {"caller": "baeko"},
                }
            )

        data = response.get_json()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(data, {"ok": False, "error": "internal_error"})
        self.assertNotIn("secret failure", str(data))


class LineWebhookFlowTest(unittest.TestCase):
    def setUp(self):
        main.processed_events.clear()

    def tearDown(self):
        main.processed_events.clear()

    def test_message_replies_processing_first_then_pushes_ai_answer(self):
        calls = []

        with patch.object(main, "webhook_executor", ImmediateExecutor()), patch.object(
            main, "reply_text", side_effect=lambda token, text: calls.append(("reply", token, text))
        ), patch.object(
            main, "push_text", side_effect=lambda to, text: calls.append(("push", to, text))
        ), patch.object(
            main, "generate_ai_reply_with_timeout", return_value="正式答案"
        ):
            main.handle_text_message(fake_line_event())

        self.assertEqual(
            calls,
            [
                ("reply", "reply-token-1", main.PROCESSING_MESSAGE),
                ("push", "user-1", "正式答案"),
            ],
        )

    def test_ai_map_is_menu_command(self):
        self.assertTrue(is_menu_command("AI地圖"))

    def test_regular_question_is_not_menu_command(self):
        self.assertFalse(is_menu_command("什麼是 Transformer？"))

    def test_menu_command_does_not_enter_ai_reply_flow(self):
        calls = []

        with main.app.test_request_context("/callback", base_url="https://example.com"):
            with patch.object(
                main,
                "handle_menu_command",
                side_effect=lambda text, api, token, base_url, assets_dir: calls.append(
                    ("menu", text, token, base_url)
                )
                or True,
            ), patch.object(
                main, "reply_text", side_effect=lambda token, text: calls.append(("reply", token, text))
            ), patch.object(
                main, "webhook_executor", ImmediateExecutor()
            ), patch.object(
                main, "generate_ai_reply_with_timeout", return_value="正式答案"
            ) as generate_ai_reply:
                main.handle_text_message(fake_line_event(text="AI地圖"))

        self.assertEqual(calls, [("menu", "AI地圖", "reply-token-1", "https://example.com")])
        generate_ai_reply.assert_not_called()

    def test_empty_ai_answer_pushes_fallback_message(self):
        calls = []

        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value=""
        ), patch.object(
            main, "push_text", side_effect=lambda to, text: calls.append((to, text))
        ):
            main.process_text_message_async("空答案問題", "user-1")

        self.assertEqual(calls, [("user-1", main.DEFAULT_FALLBACK_RESPONSE)])

    def test_none_ai_answer_uses_default_fallback_response(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value=None
        ):
            reply = main.generate_ai_reply("AI助理有沒有流量限制？")

        self.assertEqual(reply, main.DEFAULT_FALLBACK_RESPONSE)

    def test_empty_ai_answer_uses_default_fallback_response(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="   "
        ):
            reply = main.generate_ai_reply("AI助理有沒有流量限制？")

        self.assertEqual(reply, main.DEFAULT_FALLBACK_RESPONSE)

    def test_normal_ai_answer_is_preserved(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="正常答案"
        ):
            reply = main.generate_ai_reply("AI助理有沒有流量限制？")

        self.assertEqual(reply, "正常答案")

    def test_empty_rag_or_tool_result_pushes_default_fallback(self):
        calls = []

        with patch.object(
            main, "generate_ai_reply_with_timeout", return_value=""
        ), patch.object(
            main, "push_text", side_effect=lambda to, text: calls.append((to, text))
        ):
            main.process_text_message_async("AI助理有沒有流量限制？", "user-1")

        self.assertEqual(calls, [("user-1", main.DEFAULT_FALLBACK_RESPONSE)])

    def test_ai_exception_pushes_fallback_message(self):
        calls = []

        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", side_effect=RuntimeError("boom")
        ), patch.object(
            main, "push_text", side_effect=lambda to, text: calls.append((to, text))
        ):
            main.process_text_message_async("會爆炸的問題", "user-1")

        self.assertEqual(calls, [("user-1", main.ERROR_FALLBACK_RESPONSE)])

    def test_timeout_pushes_timeout_fallback_message(self):
        with patch.object(main, "ai_executor", TimeoutExecutor()):
            reply = main.generate_ai_reply_with_timeout("AI助理有沒有流量限制？", user_id="user-1")

        self.assertEqual(reply, main.TIMEOUT_FALLBACK_RESPONSE)

    def test_ai_assistant_rate_limit_question_does_not_hang(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="目前沒有已知的固定流量限制。"
        ):
            reply = main.generate_ai_reply("AI助理有沒有流量限制？")

        self.assertEqual(reply, "目前沒有已知的固定流量限制。")

    def test_duplicate_event_is_not_processed_twice(self):
        calls = []
        event = fake_line_event(event_id="duplicate-event", message_id="duplicate-message")

        with patch.object(main, "webhook_executor", ImmediateExecutor()), patch.object(
            main, "reply_text", side_effect=lambda token, text: calls.append(("reply", token, text))
        ), patch.object(
            main, "push_text", side_effect=lambda to, text: calls.append(("push", to, text))
        ), patch.object(
            main, "generate_ai_reply_with_timeout", return_value="正式答案"
        ):
            main.handle_text_message(event)
            main.handle_text_message(event)

        self.assertEqual(
            calls,
            [
                ("reply", "reply-token-1", main.PROCESSING_MESSAGE),
                ("push", "user-1", "正式答案"),
            ],
        )


class MessengerWebhookFlowTest(unittest.TestCase):
    def setUp(self):
        self.original_executor = main.messenger_webhook._background_executor
        self.original_reply_generator = main.messenger_webhook._reply_generator

    def tearDown(self):
        main.messenger_webhook.configure_messenger_handler(
            reply_generator=self.original_reply_generator,
            executor=self.original_executor,
        )

    def messenger_payload(self, messaging_event):
        return {
            "object": "page",
            "entry": [
                {
                    "messaging": [
                        messaging_event,
                    ]
                }
            ],
        }

    def test_verify_token_success_returns_challenge(self):
        with patch.dict(os.environ, {"MESSENGER_ENABLED": "true", "MESSENGER_VERIFY_TOKEN": "verify-me"}):
            response = main.app.test_client().get(
                "/webhook/messenger?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=abc123"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "abc123")

    def test_verify_token_failure_returns_403(self):
        with patch.dict(os.environ, {"MESSENGER_ENABLED": "true", "MESSENGER_VERIFY_TOKEN": "verify-me"}):
            response = main.app.test_client().get(
                "/webhook/messenger?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=abc123"
            )

        self.assertEqual(response.status_code, 403)

    def test_post_text_message_returns_200_and_submits_background_work(self):
        executor = RecordingExecutor()
        main.messenger_webhook.configure_messenger_handler(
            reply_generator=lambda user_id, text: "answer",
            executor=executor,
        )
        payload = self.messenger_payload(
            {
                "sender": {"id": "sender-1"},
                "message": {"text": "What is RAG?"},
            }
        )

        with patch.dict(os.environ, {"MESSENGER_ENABLED": "true"}), patch.object(
            main.messenger_webhook, "send_text_message", return_value=True
        ) as send_text:
            response = main.app.test_client().post("/webhook/messenger", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "OK")
        send_text.assert_called_once_with("sender-1", main.messenger_webhook.MESSENGER_PROCESSING_MESSAGE)
        self.assertEqual(len(executor.calls), 1)
        fn, args, kwargs = executor.calls[0]
        self.assertIs(fn, main.messenger_webhook.process_messenger_text_async)
        self.assertEqual(args, ("sender-1", "What is RAG?"))
        self.assertEqual(kwargs, {})

    def test_background_messenger_text_uses_tutor_user_id_and_pushes_reply(self):
        calls = []
        main.messenger_webhook.configure_messenger_handler(
            reply_generator=lambda user_id, text: calls.append((user_id, text)) or "answer",
            executor=ImmediateExecutor(),
        )

        with patch.object(
            main.messenger_webhook,
            "send_text_message",
            side_effect=lambda recipient_id, text: calls.append((recipient_id, text)) or True,
        ):
            main.messenger_webhook.process_messenger_text_async("sender-1", "What is MCP?")

        self.assertEqual(calls, [("messenger:sender-1", "What is MCP?"), ("sender-1", "answer")])

    def test_delivery_read_and_echo_events_do_not_submit_ai_flow(self):
        executor = RecordingExecutor()
        main.messenger_webhook.configure_messenger_handler(
            reply_generator=lambda user_id, text: "answer",
            executor=executor,
        )
        payload = {
            "object": "page",
            "entry": [
                {
                    "messaging": [
                        {"sender": {"id": "sender-1"}, "delivery": {"mids": ["mid-1"]}},
                        {"sender": {"id": "sender-1"}, "read": {"watermark": 123}},
                        {"sender": {"id": "sender-1"}, "message": {"text": "echo", "is_echo": True}},
                    ]
                }
            ],
        }

        with patch.object(main.messenger_webhook, "send_text_message") as send_text:
            submitted = main.messenger_webhook.handle_messenger_event(payload)

        self.assertFalse(submitted)
        self.assertEqual(executor.calls, [])
        send_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
