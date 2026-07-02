import unittest

from agents.little_tree.config import (
    EMPTY_INPUT_REPLY,
    GUIDED_LEARNING_REPLY,
    HOMEWORK_GUIDANCE_REPLY,
    ROLE_STARTER_REPLIES,
)
from agents.little_tree.intent import (
    LittleTreeIntent,
    classify_intent,
    is_guided_learning_trigger,
    match_role_starter,
)
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

    def test_role_starter_child(self):
        self.assertEqual(match_role_starter("🌱 我是小朋友"), "🌱 我是小朋友")

    def test_role_starter_parent(self):
        self.assertEqual(match_role_starter("👨‍👩‍👧 我是家長"), "👨‍👩‍👧 我是家長")

    def test_role_starter_teacher(self):
        self.assertEqual(match_role_starter("👩‍🏫 我是老師"), "👩‍🏫 我是老師")

    def test_role_starter_volunteer(self):
        self.assertEqual(match_role_starter("🤝 我是志工"), "🤝 我是志工")

    def test_role_starter_direct_chat(self):
        self.assertEqual(match_role_starter("💬 直接聊天"), "💬 直接聊天")

    def test_guided_learning_trigger(self):
        self.assertTrue(is_guided_learning_trigger("今日任務"))

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
        self.assertIn("Think together before answering", prompt)
        self.assertIn("Encourage verification", prompt)
        self.assertIn("自己的話", prompt)
        self.assertIn("parents, teachers and volunteers", prompt)
        self.assertIn("不要假裝自己是人", prompt)
        self.assertIn("不要 overclaim", prompt)


class LittleTreeRuntimePipelineTest(unittest.TestCase):
    def test_empty_input_reply_comes_from_config(self):
        runtime = LittleTreeRuntime(lambda system, user: "unused")

        self.assertEqual(runtime.answer("   "), EMPTY_INPUT_REPLY)

    def test_runtime_returns_child_starter_without_llm(self):
        calls = []
        runtime = LittleTreeRuntime(lambda system, user: calls.append((system, user)) or "unused")

        reply = runtime.answer("🌱 我是小朋友")

        self.assertEqual(reply, ROLE_STARTER_REPLIES["🌱 我是小朋友"])
        self.assertIn("AI 是什麼？", reply)
        self.assertEqual(calls, [])

    def test_runtime_returns_parent_starter_without_llm(self):
        runtime = LittleTreeRuntime(lambda system, user: "unused")

        reply = runtime.answer("👨‍👩‍👧 我是家長")

        self.assertEqual(reply, ROLE_STARTER_REPLIES["👨‍👩‍👧 我是家長"])
        self.assertIn("怎麼避免孩子依賴 AI？", reply)

    def test_runtime_returns_teacher_starter_without_llm(self):
        runtime = LittleTreeRuntime(lambda system, user: "unused")

        reply = runtime.answer("👩‍🏫 我是老師")

        self.assertEqual(reply, ROLE_STARTER_REPLIES["👩‍🏫 我是老師"])
        self.assertIn("15 分鐘 AI 課堂活動", reply)

    def test_runtime_returns_volunteer_starter_without_llm(self):
        runtime = LittleTreeRuntime(lambda system, user: "unused")

        reply = runtime.answer("🤝 我是志工")

        self.assertEqual(reply, ROLE_STARTER_REPLIES["🤝 我是志工"])
        self.assertIn("親子 AI 活動", reply)

    def test_runtime_returns_direct_chat_starter_without_llm(self):
        runtime = LittleTreeRuntime(lambda system, user: "unused")

        reply = runtime.answer("💬 直接聊天")

        self.assertEqual(reply, ROLE_STARTER_REPLIES["💬 直接聊天"])
        self.assertIn("AI 素養", reply)

    def test_runtime_returns_guided_learning_menu_without_llm(self):
        calls = []
        runtime = LittleTreeRuntime(lambda system, user: calls.append((system, user)) or "unused")

        reply = runtime.answer("今日任務")

        self.assertEqual(reply, GUIDED_LEARNING_REPLY)
        self.assertIn("問 AI 一個你真正好奇的問題", reply)
        self.assertIn("找出 AI 回答中一個需要查證的地方", reply)
        self.assertIn("把 AI 的回答改成自己的話", reply)
        self.assertEqual(calls, [])

    def test_runtime_returns_homework_boundary_without_llm(self):
        calls = []
        runtime = LittleTreeRuntime(lambda system, user: calls.append((system, user)) or "unused")

        reply = runtime.answer("幫我寫完整作文作業", user_id="child-1")

        self.assertEqual(reply, HOMEWORK_GUIDANCE_REPLY)
        self.assertIn("我不會直接給你最後答案", reply)
        self.assertIn("1. 先說說你目前想到哪裡", reply)
        self.assertIn("2. 我可以給你提示", reply)
        self.assertIn("3. 我們一起檢查你的想法", reply)
        self.assertEqual(calls, [])

    def test_runtime_passes_allowed_questions_to_llm(self):
        calls = []

        def fake_ask_gpt(system_prompt: str, user_prompt: str) -> str:
            calls.append((system_prompt, user_prompt))
            return "AI 有時會犯錯，所以要查證。"

        runtime = LittleTreeRuntime(fake_ask_gpt)
        reply = runtime.answer("AI 為什麼會犯錯？", user_id="child-1")

        self.assertEqual(reply, "AI 有時會犯錯，所以要查證。")
        self.assertIn("Intent: learning_question", calls[0][1])
        self.assertIn("Policy: allow", calls[0][1])


if __name__ == "__main__":
    unittest.main()
