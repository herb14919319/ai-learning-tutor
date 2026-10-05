from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from skills.ipas_cybersecurity import IpasCybersecuritySkill
from skills.ipas_cybersecurity.review import (ReviewError, digest, load_ledger, record_decision,
                                             record_matrix_verification, verify_source)


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ipas_cybersecurity"


class ReviewPilotWorkflowTest(unittest.TestCase):
    def test_checked_in_owner_review_closeout(self):
        processed = SKILL / "knowledge/processed"
        verify_source(processed)
        records = load_ledger(processed / "review_decisions.json")
        # Phase 5 froze the asset-management slice; later phases append their own records.
        latest = {(record["kind"], record["asset_id"]): record for record in records
                  if record["asset_id"].startswith("I11-ASSET")}
        expected = ({("chunk", f"I11-ASSET-{number:03}") for number in range(1, 8)}
                    | {("teaching", "I11-ASSET")}
                    | {("card", f"I11-ASSET-F{number:03}") for number in range(1, 11)}
                    | {("question", f"I11-ASSET-Q{number:03}") for number in range(1, 11)})
        self.assertEqual(set(latest), expected)
        self.assertTrue(all(latest[key]["decision"] == "accept" for key in expected))
        teaching_history = [record for record in records
                            if record["kind"] == "teaching" and record["asset_id"] == "I11-ASSET"]
        self.assertEqual([record["decision"] for record in teaching_history], ["revise", "accept"])
        self.assertNotEqual(teaching_history[0]["content_sha256"], teaching_history[1]["content_sha256"])

        matrix = json.loads((processed / "matrix_reviews.json").read_text(encoding="utf-8"))
        comparison = json.loads((processed / "asset_chunks.json").read_text(encoding="utf-8"))[0]["source_evidence"]["comparison"]
        manifest = json.loads((processed / "source_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix), 1)
        self.assertEqual((matrix[0]["decision"], matrix[0]["source_pages"]), ("verified", [80]))
        self.assertEqual(matrix[0]["comparison_sha256"], digest(comparison))
        self.assertEqual(matrix[0]["source_sha256"], manifest[0]["sha256"])

        skill = IpasCybersecuritySkill()
        chapter = skill.get_chapter("I11-ASSET")
        self.assertEqual(chapter["teaching_review_status"], "reviewed")
        self.assertTrue(all(chunk["teaching_interpretation"]["review_status"] == "reviewed"
                            for chunk in chapter["chunks"]))
        self.assertEqual([card["review_status"] for card in skill.get_flashcards("I11-ASSET")], ["reviewed"] * 10)
        self.assertEqual([question["review_status"] for question in skill.get_questions("I11-ASSET")], ["reviewed"] * 10)

    def test_upstream_revision_invalidates_dependents_and_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            processed, cards = Path(temp) / "processed", Path(temp) / "cards"
            shutil.copytree(SKILL / "knowledge/processed", processed)
            shutil.copytree(SKILL / "cards", cards)
            (processed / "review_decisions.json").write_text("[]\n", encoding="utf-8")
            original = json.loads((processed / "asset_chunks.json").read_text(encoding="utf-8"))
            original_explanation = original[3]["teaching_interpretation"]["explanation"]
            record_decision("chunk", "I11-ASSET-004", "accept", processed=processed, cards=cards)
            record_decision("teaching", "I11-ASSET", "accept", processed=processed, cards=cards)
            record_decision("card", "I11-ASSET-F004", "accept", processed=processed, cards=cards)
            record_decision("question", "I11-ASSET-Q003", "accept", processed=processed, cards=cards)
            skill = IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards)
            self.assertEqual(skill.get_chapter("I11-ASSET")["teaching_review_status"], "reviewed")
            self.assertEqual(next(x for x in skill.get_flashcards("I11-ASSET") if x["card_id"] == "I11-ASSET-F004")["review_status"], "reviewed")
            self.assertEqual(next(x for x in skill.get_questions("I11-ASSET") if x["question_id"] == "I11-ASSET-Q003")["review_status"], "reviewed")

            record_decision("chunk", "I11-ASSET-004", "revise", "Clarify scope before use", processed, cards)
            with self.assertRaisesRegex(ReviewError, "Revise generated content"):
                record_decision("chunk", "I11-ASSET-004", "accept", processed=processed, cards=cards)
            hidden = IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards)
            self.assertEqual(hidden.get_chapter("I11-ASSET")["markdown"], "")
            self.assertEqual(hidden.get_chapter("I11-ASSET")["teaching_blocked_by"], ["I11-ASSET-004"])
            self.assertNotIn("I11-ASSET-F004", {x["card_id"] for x in hidden.get_flashcards("I11-ASSET")})
            self.assertNotIn("I11-ASSET-Q003", {x["question_id"] for x in hidden.get_questions("I11-ASSET")})
            self.assertIsNone(hidden.query_concept("A級資產"))
            with patch.object(main.ipas_cyber_skill, "get_chapters", hidden.get_chapters), \
                 patch.object(main.ipas_cyber_skill, "get_course_info", hidden.get_course_info), \
                 patch.object(main.ipas_cyber_skill, "get_chapter", hidden.get_chapter), \
                 patch.object(main.ipas_cyber_skill, "get_flashcards", hidden.get_flashcards), \
                 patch.object(main.ipas_cyber_skill, "get_questions", hidden.get_questions), \
                 patch.object(main.ipas_cyber_skill, "submit_answer", hidden.submit_answer):
                client = main.app.test_client()
                html = client.get("/ipas/cybersecurity").get_data(as_text=True)
                self.assertIn("I11-ASSET-004", html)  # explanatory blocked-by label
                self.assertNotIn("I11-ASSET-Q003", html)
                self.assertEqual(client.post("/api/ipas/cybersecurity/answer",
                                             json={"question_id": "I11-ASSET-Q003", "answer": "A"}).status_code, 404)

            path = processed / "asset_chunks.json"
            revised = json.loads(path.read_text(encoding="utf-8"))
            revised[3]["teaching_interpretation"]["explanation"] += "（修訂後待審）"
            path.write_text(json.dumps(revised, ensure_ascii=False), encoding="utf-8")
            pending = IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards)
            self.assertEqual(next(x for x in pending.get_chapter("I11-ASSET")["chunks"]
                                  if x["chunk_id"] == "I11-ASSET-004")["teaching_interpretation"]["review_status"],
                             "pending_review")
            self.assertEqual(pending.get_chapter("I11-ASSET")["teaching_review_status"], "pending_review")
            self.assertEqual(next(x for x in pending.get_flashcards("I11-ASSET") if x["card_id"] == "I11-ASSET-F004")["review_status"], "pending_review")
            self.assertEqual(next(x for x in pending.get_questions("I11-ASSET") if x["question_id"] == "I11-ASSET-Q003")["review_status"], "pending_review")
            record_decision("chunk", "I11-ASSET-004", "accept", processed=processed, cards=cards)
            after = IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards)
            self.assertEqual(next(x for x in after.get_chapter("I11-ASSET")["chunks"]
                                  if x["chunk_id"] == "I11-ASSET-004")["teaching_interpretation"]["review_status"],
                             "reviewed")
            self.assertEqual(next(x for x in after.get_questions("I11-ASSET") if x["question_id"] == "I11-ASSET-Q003")["review_status"], "pending_review")
            ledger = json.loads((processed / "review_decisions.json").read_text(encoding="utf-8"))
            first_chunk_review = next(x for x in ledger if x["kind"] == "chunk" and x["decision"] == "accept")
            self.assertEqual(first_chunk_review["reviewed_content"]["explanation"], original_explanation)

    def test_reviewer_command_honors_source_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp) / "processed"
            shutil.copytree(SKILL / "knowledge/processed", processed)
            (processed / "review_decisions.json").write_text("[]\n", encoding="utf-8")
            manifest = json.loads((processed / "source_manifest.json").read_text(encoding="utf-8"))
            manifest[0]["sha256"] = "0" * 64
            (processed / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "source hash changed"):
                record_decision("chunk", "I11-ASSET-004", "accept", processed=processed)
            self.assertEqual(json.loads((processed / "review_decisions.json").read_text(encoding="utf-8")), [])

    def test_matrix_verification_uses_separate_hash_bound_record(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp) / "processed"
            shutil.copytree(SKILL / "knowledge/processed", processed)
            (processed / "matrix_reviews.json").write_text("[]\n", encoding="utf-8")
            source = SKILL / "knowledge/source/iPAS_資訊安全管理概論_PART_I.pdf"
            source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
            original_chunk = json.loads((processed / "asset_chunks.json").read_text(encoding="utf-8"))[0]
            record = record_matrix_verification("I11-ASSET-001", processed)
            self.assertEqual(record["source_pages"], [80])
            self.assertEqual(record["comparison_sha256"], digest(original_chunk["source_evidence"]["comparison"]))
            self.assertEqual(json.loads((processed / "matrix_reviews.json").read_text(encoding="utf-8")), [record])
            self.assertEqual(json.loads((processed / "asset_chunks.json").read_text(encoding="utf-8"))[0], original_chunk)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash_before)


if __name__ == "__main__":
    unittest.main()
