import unittest
from unittest.mock import patch

import main
from menu_router import MENU_COMMANDS
from router_guard import (
    BLOCKED_REDIRECT_MESSAGE,
    CASUAL_CHAT,
    CLARIFICATION_MESSAGE,
    LEARNING,
    LEARNING_GUIDANCE,
    TOOL_MISUSE,
    UNKNOWN,
    classify_intent,
)


class RouterGuardTest(unittest.TestCase):
    def test_ai_learning_questions_enter_tutor_flow(self):
        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="tutor answer"
        ) as answer:
            reply = main.generate_ai_reply("What is Transformer attention?")

        self.assertEqual(reply, "tutor answer")
        answer.assert_called_once_with("What is Transformer attention?", user_id=None)
        self.assertEqual(classify_intent("What is Transformer attention?"), LEARNING)

    def test_beginner_learning_guidance_enters_tutor_flow(self):
        text = "I'm a beginner. Where should I start learning LLMs?"

        with patch.object(main, "openai_client", object()), patch.object(
            main.tutor_agent, "answer", return_value="learning plan"
        ) as answer:
            reply = main.generate_ai_reply(text)

        self.assertEqual(reply, "learning plan")
        answer.assert_called_once_with(text, user_id=None)
        self.assertEqual(classify_intent(text), LEARNING_GUIDANCE)

    def test_image_generation_requests_are_blocked_without_tutor_call(self):
        with patch.object(main.tutor_agent, "answer") as answer:
            reply = main.generate_ai_reply("Generate an image of a futuristic classroom.")

        self.assertEqual(reply, BLOCKED_REDIRECT_MESSAGE)
        answer.assert_not_called()
        self.assertEqual(classify_intent("Generate an image of a futuristic classroom."), TOOL_MISUSE)

    def test_casual_chat_is_blocked_without_tutor_call(self):
        with patch.object(main.tutor_agent, "answer") as answer:
            reply = main.generate_ai_reply("Hi, how are you?")

        self.assertEqual(reply, BLOCKED_REDIRECT_MESSAGE)
        answer.assert_not_called()
        self.assertEqual(classify_intent("Hi, how are you?"), CASUAL_CHAT)

    def test_roleplay_girlfriend_and_fortune_telling_are_blocked(self):
        examples = [
            "Roleplay as my girlfriend.",
            "Be my girlfriend and text me tonight.",
            "Tell my fortune with tarot.",
        ]

        for text in examples:
            with self.subTest(text=text), patch.object(main.tutor_agent, "answer") as answer:
                reply = main.generate_ai_reply(text)

                self.assertEqual(reply, BLOCKED_REDIRECT_MESSAGE)
                answer.assert_not_called()
                self.assertEqual(classify_intent(text), TOOL_MISUSE)

    def test_ambiguous_messages_get_clarification_without_tutor_call(self):
        with patch.object(main.tutor_agent, "answer") as answer:
            reply = main.generate_ai_reply("Can you help me with this?")

        self.assertEqual(reply, CLARIFICATION_MESSAGE)
        answer.assert_not_called()
        self.assertEqual(classify_intent("Can you help me with this?"), UNKNOWN)

    def test_rich_menu_commands_still_bypass_tutor_flow(self):
        command = next(iter(MENU_COMMANDS))
        calls = []

        with main.app.test_request_context("/callback", base_url="https://example.com"):
            with patch.object(
                main,
                "handle_menu_command",
                side_effect=lambda text, api, token, base_url, assets_dir: calls.append(
                    ("menu", text, token, base_url)
                )
                or True,
            ), patch.object(main, "generate_ai_reply_with_timeout") as generate_ai_reply:
                main.handle_text_message(
                    type(
                        "FakeEvent",
                        (),
                        {
                            "reply_token": "reply-token-1",
                            "webhook_event_id": "event-rich-menu",
                            "source": type("Source", (), {"user_id": "user-1"})(),
                            "message": type("Message", (), {"id": "message-rich-menu", "text": command})(),
                        },
                    )()
                )

        self.assertEqual(calls, [("menu", command, "reply-token-1", "https://example.com")])
        generate_ai_reply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
