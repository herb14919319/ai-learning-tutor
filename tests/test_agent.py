import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
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


if __name__ == "__main__":
    unittest.main()
