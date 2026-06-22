import unittest
from unittest.mock import patch

from agents.router import route
from agents.tutor_agent import TutorAgent
from skills.registry import get_skill_metadata, list_skills
from skills.runtime import SkillCatalog, SkillManifest, SkillRuntime


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


if __name__ == "__main__":
    unittest.main()
