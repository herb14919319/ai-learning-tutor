from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import main
from skills.ipas_cybersecurity import ContentFormatError, IpasCybersecuritySkill
from skills.registry import get_runtime, get_skill_metadata


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "ipas_cybersecurity"


class CybersecurityCiaSliceTest(unittest.TestCase):
    def setUp(self):
        self.skill = IpasCybersecuritySkill()

    def test_schema_and_canonical_source_references(self):
        schema = json.loads((SKILL_ROOT / "knowledge/processed/learning_chunk_schema_v0_1.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["schema_version"], "0.1")
        chunks = self.skill.get_chapter()["chunks"]
        self.assertEqual(len(chunks), 4)
        self.assertEqual({item["chunk_id"] for item in chunks}, {f"I11-CIA-{number:03d}" for number in range(1, 5)})
        for chunk in chunks:
            self.assertTrue(set(schema["required"]) <= chunk.keys())
            self.assertTrue(set(schema["source_evidence_required"]) <= chunk["source_evidence"].keys())
            self.assertTrue(set(schema["teaching_interpretation_required"]) <= chunk["teaching_interpretation"].keys())
            evidence = chunk["source_evidence"]
            self.assertEqual(evidence["source_file"], "iPAS_資訊安全管理概論_PART_I.pdf")
            self.assertTrue(set(evidence["source_pages"]) <= {13, 15, 16, 17})
            self.assertTrue(evidence["source_title"])
            self.assertTrue(evidence["observations"])

    def test_teaching_cards_and_quiz_are_connected(self):
        chapter = self.skill.get_chapter()
        self.assertIn("# I11 資訊安全管理概論：CIA 三目標", chapter["markdown"])
        self.assertIn("生成的教學示例", chapter["markdown"])
        chunk_ids = {chunk["chunk_id"] for chunk in chapter["chunks"]}
        cards = self.skill.get_flashcards()
        questions = self.skill.get_questions()
        self.assertEqual(len(cards), 6)
        self.assertEqual(len(questions), 6)
        self.assertTrue(all(set(item["chunk_ids"]) <= chunk_ids for item in cards + questions))
        self.assertTrue(all("correct_answer" not in question and "explanation" not in question for question in questions))
        self.assertTrue(all(item["content_origin"] == "generated_teaching" for item in cards))
        self.assertEqual({item["cognitive_level"] for item in questions}, {"recall", "distinction", "scenario"})

    def test_runtime_discovery_and_existing_skills(self):
        self.assertIsNotNone(get_skill_metadata("ipas_cybersecurity"))
        runtime = get_runtime()
        self.assertEqual(runtime.route(runtime.normalize_request("iPAS 資訊安全工程師 CIA"))["skill"], "ipas_cybersecurity")
        self.assertEqual(runtime.route(runtime.normalize_request("iPAS 資安風險"))["skill"], "ipas_cybersecurity")
        self.assertEqual(runtime.route(runtime.normalize_request("iPAS 風險評鑑流程"))["skill"], "ipas_cybersecurity")
        self.assertIn("機密性", runtime.invoke("ipas_cybersecurity", runtime.normalize_request("CIA 機密性")))
        self.assertIn("脆弱性", runtime.invoke("ipas_cybersecurity", runtime.normalize_request("iPAS 資安風險中的脆弱性")))
        self.assertIn("風險評鑑", runtime.invoke("ipas_cybersecurity", runtime.normalize_request("iPAS 風險評鑑流程")))
        self.assertEqual(runtime.route(runtime.normalize_request("我要準備 iPAS AI 應用規劃師"))["skill"], "ipas_ai_application_planner")
        self.assertIsNotNone(get_skill_metadata("ipas_net_zero_planner"))

    def test_web_page_and_backend_grading(self):
        client = main.app.test_client()
        response = client.get("/ipas/cybersecurity")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("CIA 三目標", html)
        self.assertIn("iPAS_資訊安全管理概論_PART_I.pdf", html)
        self.assertNotIn('"correct_answer"', html)
        graded = client.post("/api/ipas/cybersecurity/answer", json={"question_id": "I11-CIA-Q001", "answer": "B"})
        self.assertEqual(graded.status_code, 200)
        self.assertTrue(graded.get_json()["correct"])
        self.assertEqual(graded.get_json()["source_references"][0]["source_pages"], [13, 15, 16])
        self.assertEqual(client.post("/api/ipas/cybersecurity/answer", json={"question_id": "I11-CIA-Q999", "answer": "A"}).status_code, 404)

    def test_risk_chunks_use_v02_relationships_and_valid_source_pages(self):
        schema = json.loads((SKILL_ROOT / "knowledge/processed/learning_chunk_schema_v0_2.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["schema_version"], "0.2")
        self.assertEqual(schema["extends"], "learning_chunk_schema_v0_1.json")
        chapter = self.skill.get_chapter("I11-RISK")
        chunks = chapter["chunks"]
        self.assertEqual(len(chunks), 5)
        ids = {chunk["chunk_id"] for chunk in chunks}
        self.assertEqual(len(ids), 5)
        relations = []
        for chunk in chunks:
            self.assertTrue(set(schema["required"]) <= chunk.keys())
            self.assertTrue(set(chunk["source_evidence"]["source_pages"]) <= {92, 93, 95})
            self.assertEqual(chunk["teaching_interpretation"]["review_status"], "pending_review")
            for relation in chunk.get("relationships", []):
                self.assertIn(relation["target_chunk_id"], ids)
                self.assertIn(relation["predicate"], schema["relationship_predicates"])
                relations.append((chunk["chunk_id"], relation["predicate"], relation["target_chunk_id"]))
        self.assertIn(("I11-RISK-002", "exploits", "I11-RISK-003"), relations)
        self.assertIn(("I11-RISK-003", "belongs_to", "I11-RISK-001"), relations)
        self.assertIn(("I11-RISK-004", "contributes_to", "I11-RISK-005"), relations)
        self.assertEqual(self.skill.get_chapter("I11-CIA")["chunks"][0]["chunk_id"], "I11-CIA-001")

    def test_risk_teaching_cards_questions_and_web(self):
        chapter = self.skill.get_chapter("I11-RISK")
        self.assertIn("Review status: `pending_review`", chapter["markdown"])
        ids = {chunk["chunk_id"] for chunk in chapter["chunks"]}
        cards = self.skill.get_flashcards("I11-RISK")
        questions = self.skill.get_questions("I11-RISK")
        self.assertEqual(len(cards), 6)
        self.assertEqual(len(questions), 6)
        self.assertTrue(all(set(item["chunk_ids"]) <= ids for item in cards + questions))
        self.assertTrue(all(item["review_status"] == "pending_review" for item in cards + questions))
        self.assertTrue(all("correct_answer" not in item and "explanation" not in item for item in questions))
        self.assertEqual({item["cognitive_level"] for item in questions}, {"recall", "distinction", "scenario"})
        client = main.app.test_client()
        html = client.get("/ipas/cybersecurity").get_data(as_text=True)
        self.assertIn("I11-RISK-Q001", html)
        self.assertIn("威脅、脆弱性與風險", html)
        self.assertNotIn('"correct_answer"', html)
        graded = client.post("/api/ipas/cybersecurity/answer", json={"question_id": "I11-RISK-Q001", "answer": "A"})
        self.assertEqual(graded.status_code, 200)
        self.assertTrue(graded.get_json()["correct"])
        self.assertTrue(all(set(ref["source_pages"]) <= {92, 93, 95} for ref in graded.get_json()["source_references"]))

    def test_changed_source_hash_and_broken_relation_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp) / "processed"
            shutil.copytree(SKILL_ROOT / "knowledge/processed", processed)
            manifest_path = processed / "source_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest[0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentFormatError, "PDF 已變更"):
                IpasCybersecuritySkill(processed_dir=processed).get_chapters()
            shutil.copy2(SKILL_ROOT / "knowledge/processed/source_manifest.json", manifest_path)
            chunk_path = processed / "risk_chunks.json"
            chunks = json.loads(chunk_path.read_text(encoding="utf-8"))
            chunks[1]["relationships"][0]["target_chunk_id"] = "MISSING-CHUNK"
            chunk_path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentFormatError, "關係目標無效"):
                IpasCybersecuritySkill(processed_dir=processed).get_chapters()

    def test_assessment_v03_explicit_sequence_and_citations(self):
        schema = json.loads((SKILL_ROOT / "knowledge/processed/learning_chunk_schema_v0_3.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["schema_version"], "0.3")
        self.assertEqual(schema["extends"], "learning_chunk_schema_v0_2.json")
        self.assertEqual(set(schema["relationship_predicates"]) - {"exploits", "belongs_to", "contributes_to"}, {"precedes"})
        chapter = self.skill.get_chapter("I11-ASSESS")
        chunks = chapter["chunks"]
        self.assertEqual(len(chunks), 4)
        self.assertEqual([chunk["chunk_id"] for chunk in chunks], [f"I11-ASSESS-{number:03d}" for number in range(1, 5)])
        self.assertEqual([chunk["chunk_type"] for chunk in chunks[1:]], ["process"] * 3)
        edges = [
            (chunk["chunk_id"], relation["target_chunk_id"])
            for chunk in chunks for relation in chunk.get("relationships", [])
            if relation["predicate"] == "precedes"
        ]
        self.assertEqual(edges, [("I11-ASSESS-002", "I11-ASSESS-003"), ("I11-ASSESS-003", "I11-ASSESS-004")])
        for chunk in chunks:
            evidence = chunk["source_evidence"]
            self.assertEqual(evidence["source_file"], "iPAS_資訊安全管理概論_PART_I.pdf")
            self.assertTrue((SKILL_ROOT / "knowledge/source" / evidence["source_file"]).is_file())
            self.assertTrue(all(1 <= page <= 114 and page in {103, 105} for page in evidence["source_pages"]))
            self.assertTrue(evidence["source_title"])
            self.assertEqual(chunk["teaching_interpretation"]["review_status"], "pending_review")
        self.assertEqual(len(self.skill.get_chapter("I11-CIA")["chunks"]), 4)
        self.assertEqual(len(self.skill.get_chapter("I11-RISK")["chunks"]), 5)

    def test_assessment_assets_web_and_api(self):
        chapter = self.skill.get_chapter("I11-ASSESS")
        self.assertIn("Review status: `pending_review`", chapter["markdown"])
        ids = {chunk["chunk_id"] for chunk in chapter["chunks"]}
        cards = self.skill.get_flashcards("I11-ASSESS")
        questions = self.skill.get_questions("I11-ASSESS")
        self.assertEqual(len(cards), 6)
        self.assertEqual(len(questions), 6)
        self.assertTrue(all(item["review_status"] == "pending_review" and set(item["chunk_ids"]) <= ids for item in cards + questions))
        self.assertTrue(all("correct_answer" not in question and "explanation" not in question for question in questions))
        client = main.app.test_client()
        response = client.get("/ipas/cybersecurity")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("I11-ASSESS-Q001", html)
        self.assertIn("風險評鑑三步驟", html)
        self.assertNotIn('"correct_answer"', html)
        graded = client.post("/api/ipas/cybersecurity/answer", json={"question_id": "I11-ASSESS-Q001", "answer": "B"})
        self.assertEqual(graded.status_code, 200)
        self.assertTrue(graded.get_json()["correct"])
        self.assertTrue(all(set(ref["source_pages"]) <= {103, 105} for ref in graded.get_json()["source_references"]))

    def test_assessment_cycle_reverse_and_cross_slice_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            processed = Path(temp) / "processed"
            shutil.copytree(SKILL_ROOT / "knowledge/processed", processed)
            chunk_path = processed / "assessment_chunks.json"
            original = json.loads(chunk_path.read_text(encoding="utf-8"))

            cyclic = json.loads(json.dumps(original))
            cyclic[3]["relationships"] = [{"predicate": "precedes", "target_chunk_id": "I11-ASSESS-002"}]
            chunk_path.write_text(json.dumps(cyclic, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentFormatError, "順序|循環"):
                IpasCybersecuritySkill(processed_dir=processed).get_chapters()

            reversed_link = json.loads(json.dumps(original))
            reversed_link[1]["relationships"] = []
            reversed_link[2]["relationships"] = [{"predicate": "precedes", "target_chunk_id": "I11-ASSESS-002"}]
            chunk_path.write_text(json.dumps(reversed_link, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentFormatError, "順序方向"):
                IpasCybersecuritySkill(processed_dir=processed).get_chapters()

            cross_slice = json.loads(json.dumps(original))
            cross_slice[1]["relationships"][0]["target_chunk_id"] = "I11-RISK-003"
            chunk_path.write_text(json.dumps(cross_slice, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContentFormatError, "不可跨切片"):
                IpasCybersecuritySkill(processed_dir=processed).get_chapters()


if __name__ == "__main__":
    unittest.main()
