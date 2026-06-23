import unittest

from agents.tutor_agent import TutorAgent
from memory.conversation_context import MAX_CONTEXT_TURNS
from memory.conversation_context import add_turn
from memory.conversation_context import build_user_prompt
from memory.conversation_context import clear_context
from memory.conversation_context import get_recent_context
from skills.runtime import SkillCatalog, SkillRuntime


class ConversationContextTest(unittest.TestCase):
    def setUp(self):
        clear_context()

    def tearDown(self):
        clear_context()

    def test_same_user_can_read_previous_turn_context(self):
        add_turn("user-1", "What is Skill?", "Skill is an SOP.")

        context = get_recent_context("user-1")

        self.assertEqual(
            context,
            [
                {"role": "user", "content": "What is Skill?"},
                {"role": "assistant", "content": "Skill is an SOP."},
            ],
        )

    def test_different_users_do_not_share_context(self):
        add_turn("user-1", "What is Skill?", "Skill is an SOP.")
        add_turn("user-2", "What is RAG?", "RAG retrieves context.")

        self.assertEqual(get_recent_context("user-1")[0]["content"], "What is Skill?")
        self.assertEqual(get_recent_context("user-2")[0]["content"], "What is RAG?")

    def test_context_is_trimmed_to_six_turns(self):
        for index in range(MAX_CONTEXT_TURNS + 2):
            add_turn("user-1", f"question-{index}", f"answer-{index}")

        context = get_recent_context("user-1")

        self.assertEqual(len(context), MAX_CONTEXT_TURNS * 2)
        self.assertEqual(context[0]["content"], "question-2")
        self.assertEqual(context[-1]["content"], "answer-7")

    def test_empty_context_falls_back_to_single_turn_prompt(self):
        prompt = build_user_prompt("OK", "user-1")

        self.assertEqual(prompt, "學生問題：OK")

    def test_empty_context_after_restart_still_answers_normally(self):
        add_turn("user-1", "What is Skill?", "Skill is an SOP.")
        clear_context()
        prompts = []

        def fake_ask_gpt(system_prompt: str, user_prompt: str) -> str:
            prompts.append(user_prompt)
            return "single turn answer"

        runtime = SkillRuntime(SkillCatalog(()))
        agent = TutorAgent(fake_ask_gpt, skill_runtime=runtime)

        answer = agent.answer("OK", user_id="user-1")

        self.assertEqual(answer, "single turn answer")
        self.assertEqual(prompts, ["學生問題：OK"])

    def test_agent_injects_recent_context_before_general_prompt(self):
        prompts = []

        def fake_ask_gpt(system_prompt: str, user_prompt: str) -> str:
            prompts.append(user_prompt)
            return f"answer-{len(prompts)}"

        runtime = SkillRuntime(SkillCatalog(()))
        agent = TutorAgent(fake_ask_gpt, skill_runtime=runtime)

        agent.answer("What is Skill?", user_id="user-1")
        agent.answer("OK", user_id="user-1")

        self.assertIn("最近對話：", prompts[1])
        self.assertIn("User: What is Skill?", prompts[1])
        self.assertIn("Assistant: answer-1", prompts[1])
        self.assertTrue(prompts[1].endswith("學生問題：OK"))


if __name__ == "__main__":
    unittest.main()
