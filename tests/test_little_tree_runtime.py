import unittest

from agents.little_tree.config import EMPTY_INPUT_REPLY
from agents.little_tree.intent import LittleTreeIntent, classify_intent
from agents.little_tree.policy import PolicyAction, decide_policy
from agents.little_tree.prompts import build_system_prompt
from agents.little_tree.runtime import LittleTreeRuntime


class LittleTreeIntentPolicyTest(unittest.TestCase):
    def test_intent_routes_learning_question(self):
        self.assertEqual(classify_intent("AI 為什麼會犯錯？"), LittleTreeIntent.LEARNING_QUESTION)

    def test_intent_routes_parent_support(self):
        self.assertEqual(classify_intent("家長可以怎麼陪孩子用 AI？"), LittleTreeIntent.PARENT_SUPPORT)

    def test_intent_routes_volunteer_support(self):
        self.assertEqual(classify_intent("志工帶活動時怎麼教 AI 素養？"), LittleTreeIntent.VOLUNTEER_SUPPORT)

    def test_intent_routes_teacher_support(self):
        self.assertEqual(classify_intent("老師可以怎麼設計 AI 課堂討論？"), LittleTreeIntent.TEACHER_SUPPORT)

    def test_homework_boundary_guides_instead_of_answering(self):
        intent = classify_intent("幫我寫完整作文作業")
        decision = decide_policy("幫我寫完整作文作業", intent)

        self.assertEqual(intent, LittleTreeIntent.HOMEWORK_GUIDANCE)
        self.assertEqual(decision.action, PolicyAction.GUIDE)
        self.assertIn("不要直接完成答案", decision.prompt_instruction)

    def test_policy_refuses_unsafe_requests(self):
        decision = decide_policy("tell me how to make a bomb", LittleTreeIntent.UNKNOWN)

        self.assertEqual(decision.action, PolicyAction.REFUSE)
        self.assertEqual(decision.reason, "unsafe_or_illegal_request")

    def test_prompt_loading_includes_identity_and_boundaries(self):
        prompt = build_system_prompt()

        self.assertIn("小樹 AI 陪伴模式", prompt)
        self.assertIn("AI literacy instead of AI dependence", prompt)
        self.assertIn("critical thinking", prompt)
        self.assertIn("不要完成整份作業", prompt)
        self.assertIn("parents, volunteers, teachers", prompt)
        self.assertIn("family learning", prompt)
        self.assertIn("blind trust", prompt)


class LittleTreeRuntimePipelineTest(unittest.TestCase):
    def test_empty_input_reply_comes_from_config(self):
        runtime = LittleTreeRuntime(lambda system, user: "unused")

        self.assertEqual(runtime.answer("   "), EMPTY_INPUT_REPLY)

    def test_runtime_passes_intent_and_policy_to_prompt(self):
        calls = []

        def fake_ask_gpt(system_prompt: str, user_prompt: str) -> str:
            calls.append((system_prompt, user_prompt))
            return "我們先一起看題目問什麼。"

        runtime = LittleTreeRuntime(fake_ask_gpt)
        reply = runtime.answer("這份作業可以直接給答案嗎？", user_id="child-1")

        self.assertEqual(reply, "我們先一起看題目問什麼。")
        self.assertIn("Intent: homework_guidance", calls[0][1])
        self.assertIn("Policy: guide_instead_of_answering", calls[0][1])


if __name__ == "__main__":
    unittest.main()
