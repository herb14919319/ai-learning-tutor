import unittest
from pathlib import Path
from unittest.mock import patch

import main
from skills.fa.retriever import FaRetriever
from skills.fa.skill import BOUNDARY_MESSAGE, NO_DATA_MESSAGE, FaSkill


ROOT = Path(__file__).resolve().parents[1]


class RecordingModel:
    def __init__(self, answer="功能名稱：測試功能\n適用端別：管理端\n功能位置：測試位置\n操作步驟：測試步驟\n注意事項：無\n資料不足說明：無"):
        self.answer = answer
        self.calls = []

    def __call__(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.answer


class FaSkillTest(unittest.TestCase):
    def setUp(self):
        self.retriever = FaRetriever(
            ROOT / "skills" / "fa" / "config.json",
            ROOT / "skills" / "fa" / "knowledge" / "index.json",
        )

    def test_fa_uses_isolated_prompt_and_knowledge(self):
        model = RecordingModel()
        answer = FaSkill(model, retriever=self.retriever).answer("管理端如何新增社區公告？")

        self.assertEqual(len(model.calls), 1)
        system_prompt, user_prompt = model.calls[0]
        self.assertIn("FA 功能查詢小幫手", system_prompt)
        self.assertIn("模組：社區公告", system_prompt)
        self.assertIn("[手冊頁碼：", system_prompt)
        self.assertIn("管理端如何新增社區公告", user_prompt)
        self.assertIn("手冊頁碼：", answer)
        for field in ("功能名稱：", "適用端別：", "功能位置：", "操作步驟：", "注意事項：", "手冊頁碼：", "資料不足說明："):
            self.assertIn(field, answer)

    def test_model_cannot_invent_manual_page_number(self):
        model = RecordingModel(answer="功能名稱：新增公告\n手冊頁碼：999")
        answer = FaSkill(model, retriever=self.retriever).answer("如何新增社區公告？")

        self.assertNotIn("999", answer)
        self.assertIn("手冊頁碼：", answer)

    def test_management_and_resident_results_are_isolated(self):
        management = self.retriever.search("管理端如何建立訪客預約？")
        resident = self.retriever.search("住戶端如何建立訪客預約？")

        self.assertTrue(management)
        self.assertTrue(resident)
        self.assertTrue(all(item.metadata["user_side"] in {"management", "both"} for item in management))
        self.assertTrue(all(item.metadata["user_side"] in {"resident", "both"} for item in resident))
        self.assertIn(118, {item.metadata["page_start"] for item in management})
        self.assertIn(131, {item.metadata["page_start"] for item in resident})

    def test_unknown_question_does_not_invent_steps_or_call_model(self):
        model = RecordingModel()
        answer = FaSkill(model, retriever=self.retriever).answer("火星電梯要怎麼傳送？")

        self.assertEqual(model.calls, [])
        self.assertIn(NO_DATA_MESSAGE, answer)
        self.assertNotIn("點選", answer)

    def test_realtime_queries_return_capability_boundary_without_model(self):
        for question in ("我的包裹目前狀態？", "管理費是否已繳？", "訪客現在到了嗎？"):
            with self.subTest(question=question):
                model = RecordingModel()
                answer = FaSkill(model, retriever=self.retriever).answer(question)
                self.assertEqual(model.calls, [])
                self.assertIn(BOUNDARY_MESSAGE, answer)

    def test_relevant_retrieval_includes_manual_page(self):
        results = self.retriever.search("瓦斯抄錶如何通知住戶？")
        self.assertIn(9, {item.metadata["page_start"] for item in results})


class FaWebRouteTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()
        main.fa_web_rate_limits.clear()

    def test_fa_page_opens_and_posts_explicit_skill_id(self):
        response = self.client.get("/fa")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("FA 功能查詢小幫手", html)
        self.assertIn('skill_id: "fa"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("overflow-x: hidden", html)

    def test_skill_id_fa_dispatches_fa_only(self):
        with patch.object(main.fa_skill, "answer", return_value="FA answer") as fa_answer, patch.object(
            main, "generate_ai_reply", return_value="Tutor answer"
        ) as tutor_answer:
            response = self.client.post(
                "/web-chat",
                json={"message": "如何新增公告？", "user_id": "fa-test", "skill_id": "fa"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reply"], "FA answer")
        self.assertEqual(response.get_json()["skill_id"], "fa")
        fa_answer.assert_called_once_with("如何新增公告？")
        tutor_answer.assert_not_called()

    def test_existing_web_chat_still_dispatches_tutor(self):
        with patch.object(main, "generate_ai_reply", return_value="Tutor answer") as tutor_answer, patch.object(
            main.fa_skill, "answer", return_value="FA answer"
        ) as fa_answer:
            response = self.client.post("/web-chat", json={"message": "什麼是 RAG？", "user_id": "tutor-test"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reply"], "Tutor answer")
        tutor_answer.assert_called_once()
        fa_answer.assert_not_called()

    def test_unknown_skill_id_is_rejected(self):
        response = self.client.post("/web-chat", json={"message": "hello", "skill_id": "unknown"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "unsupported_skill")


if __name__ == "__main__":
    unittest.main()
