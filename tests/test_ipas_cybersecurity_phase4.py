from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import main
from skills.ipas_cybersecurity import ContentFormatError, IpasCybersecuritySkill
from skills.ipas_cybersecurity.review import ReviewError, find_asset, record_decision
from skills.registry import get_runtime


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "ipas_cybersecurity"


class CybersecurityPhase4Test(unittest.TestCase):
    def setUp(self):
        self.skill = IpasCybersecuritySkill()

    def test_v04_comparison_and_previous_slices(self):
        schema = json.loads((SKILL_ROOT / "knowledge/processed/learning_chunk_schema_v0_4.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["extends"], "learning_chunk_schema_v0_3.json")
        chapter = self.skill.get_chapter("I11-ASSET")
        self.assertEqual(chapter["source_pages"], [77, 78, 79, 80])
        self.assertEqual(len(chapter["chunks"]), 7)
        matrix = chapter["chunks"][0]["source_evidence"]["comparison"]
        self.assertEqual(matrix["members"], [f"I11-ASSET-{i:03}" for i in range(4, 8)])
        self.assertEqual([dimension["key"] for dimension in matrix["dimensions"]],
                         ["affected_scope", "business_effect", "potential_impact"])
        self.assertEqual([cell["value"] for cell in matrix["dimensions"][2]["values"]],
                         ["極高度", "高度", "中度", "低度"])
        self.assertEqual([cell["value"] for cell in matrix["dimensions"][1]["values"][:3]],
                         ["持續一個月（含）以上", "持續一星期（含）以上", "持續一天（含）以上"])
        self.assertTrue(all(cell["source_page"] == 80 for dimension in matrix["dimensions"] for cell in dimension["values"]))
        self.assertTrue(all(chunk["teaching_interpretation"]["review_status"] in {"pending_review", "reviewed"}
                            for chunk in chapter["chunks"]))
        self.assertEqual([len(self.skill.get_chapter(name)["chunks"]) for name in ("I11-CIA", "I11-RISK", "I11-ASSESS")],
                         [4, 5, 4])

    def test_assets_answer_hiding_web_and_tutor(self):
        ids = {chunk["chunk_id"] for chunk in self.skill.get_chapter("I11-ASSET")["chunks"]}
        cards = self.skill.get_flashcards("I11-ASSET")
        questions = self.skill.get_questions("I11-ASSET")
        self.assertEqual((len(cards), len(questions)), (10, 10))
        self.assertTrue(all(set(item["chunk_ids"]) <= ids and item["review_status"] in {"pending_review", "reviewed"}
                            for item in cards + questions))
        self.assertTrue(all("correct_answer" not in item and "explanation" not in item for item in questions))
        self.assertEqual({item["cognitive_level"] for item in questions}, {"recall", "distinction", "comparison", "scenario"})
        client = main.app.test_client()
        html = client.get("/ipas/cybersecurity").get_data(as_text=True)
        self.assertIn("I11-ASSET-Q001", html)
        self.assertIn("pending_review", html)
        self.assertNotIn('"correct_answer"', html)
        response = client.post("/api/ipas/cybersecurity/answer", json={"question_id": "I11-ASSET-Q004", "answer": "A"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["correct"])
        self.assertTrue(all(80 in ref["source_pages"] for ref in response.get_json()["source_references"]))
        self.assertEqual(self.skill.query_concept("資產價值分類")["chunk_id"], "I11-ASSET-001")
        runtime = get_runtime()
        self.assertEqual(runtime.route(runtime.normalize_request("iPAS 資訊安全工程師 資產分類"))["skill"], "ipas_cybersecurity")

    def test_invalid_comparison_and_question_references(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp) / "processed"
            shutil.copytree(SKILL_ROOT / "knowledge/processed", processed)
            path = processed / "asset_chunks.json"
            original = json.loads(path.read_text(encoding="utf-8"))

            def invalid(mutator, pattern):
                data = json.loads(json.dumps(original))
                mutator(data)
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                with self.assertRaisesRegex(ContentFormatError, pattern):
                    IpasCybersecuritySkill(processed_dir=processed).get_chapters()

            invalid(lambda data: data[0]["source_evidence"]["comparison"]["members"].append("MISSING"), "比較成員")
            invalid(lambda data: data[0]["source_evidence"]["comparison"]["dimensions"].append(
                data[0]["source_evidence"]["comparison"]["dimensions"][0]), "比較維度重複")
            invalid(lambda data: data[0]["source_evidence"]["comparison"]["dimensions"][0]["values"][1].update(
                member_chunk_id="I11-ASSET-004"), "比較值")
            invalid(lambda data: data[0]["source_evidence"]["comparison"]["dimensions"][0]["values"][0].update(
                source_page=81), "來源頁")
            path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            questions_path = processed / "asset_questions.json"
            questions = json.loads(questions_path.read_text(encoding="utf-8"))
            questions[2]["comparison_chunk_id"] = "I11-ASSET-003"
            questions_path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentFormatError, "比較表"):
                IpasCybersecuritySkill(processed_dir=processed).get_chapters()

    def test_review_decisions_source_immutability_and_stale_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp) / "processed"
            cards = Path(temp) / "cards"
            shutil.copytree(SKILL_ROOT / "knowledge/processed", processed)
            shutil.copytree(SKILL_ROOT / "cards", cards)
            source_path = SKILL_ROOT / "knowledge/source/iPAS_資訊安全管理概論_PART_I.pdf"
            before = hashlib.sha256(source_path.read_bytes()).hexdigest()
            with self.assertRaises(ReviewError):
                find_asset("source", "SRC-I11-MGMT-I", processed, cards)
            with self.assertRaisesRegex(ReviewError, "note"):
                record_decision("question", "I11-ASSET-Q001", "revise", processed=processed, cards=cards)
            accepted = record_decision("question", "I11-ASSET-Q001", "accept", processed=processed, cards=cards)
            self.assertEqual(accepted["decision"], "accept")
            self.assertTrue(accepted["reviewed_at"])
            record_decision("question", "I11-ASSET-Q001", "revise", "收緊題幹條件", processed, cards)
            self.assertNotIn("I11-ASSET-Q001", {q["question_id"] for q in IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards).get_questions("I11-ASSET")})
            with self.assertRaisesRegex(ReviewError, "Revise generated content"):
                record_decision("question", "I11-ASSET-Q001", "accept", "複核完成", processed, cards)
            revised_path = processed / "asset_questions.json"
            revised_questions = json.loads(revised_path.read_text(encoding="utf-8"))
            revised_questions[0]["question"] += "（明確條件）"
            revised_path.write_text(json.dumps(revised_questions, ensure_ascii=False), encoding="utf-8")
            record_decision("question", "I11-ASSET-Q001", "accept", "複核完成", processed, cards)
            revised = record_decision("card", "I11-ASSET-F001", "revise", "請重寫卡片背面", processed, cards)
            self.assertEqual(revised["note"], "請重寫卡片背面")
            record_decision("question", "I11-ASSET-Q002", "reject", "條件不足", processed, cards)
            skill = IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards)
            self.assertEqual(next(q for q in skill.get_questions("I11-ASSET") if q["question_id"] == "I11-ASSET-Q001")["review_status"], "reviewed")
            self.assertNotIn("I11-ASSET-Q002", {q["question_id"] for q in skill.get_questions("I11-ASSET")})
            self.assertNotIn("I11-ASSET-F001", {c["card_id"] for c in skill.get_flashcards("I11-ASSET")})
            self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), before)
            path = processed / "asset_questions.json"
            questions = json.loads(path.read_text(encoding="utf-8"))
            questions[0]["question"] += "（改稿）"
            path.write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")
            fresh = IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards)
            self.assertEqual(next(q for q in fresh.get_questions("I11-ASSET") if q["question_id"] == "I11-ASSET-Q001")["review_status"], "pending_review")

    def test_rejected_chunk_hides_dependents_and_invalid_review_state(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp) / "processed"
            shutil.copytree(SKILL_ROOT / "knowledge/processed", processed)
            record_decision("chunk", "I11-ASSET-004", "reject", "來源解釋需重寫", processed)
            skill = IpasCybersecuritySkill(processed_dir=processed)
            self.assertNotIn("I11-ASSET-004", {c["chunk_id"] for c in skill.get_chapter("I11-ASSET")["chunks"]})
            self.assertNotIn("I11-ASSET-Q003", {q["question_id"] for q in skill.get_questions("I11-ASSET")})
            self.assertEqual(len(skill.get_chapter("I11-CIA")["chunks"]), 4)
            ledger_path = processed / "review_decisions.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger[0]["decision"] = "official"
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            with self.assertRaisesRegex(ContentFormatError, "審核紀錄"):
                IpasCybersecuritySkill(processed_dir=processed).get_chapters()


if __name__ == "__main__":
    unittest.main()
