"""R4: the Knowledge Pack contract, its optional capabilities, and pack-specific safeguards."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main
import tests
from knowledge_packs import (
    COURSE_INFO_FIELDS,
    GRADING_FIELDS,
    HIDDEN_QUESTION_FIELDS,
    QUESTION_FIELDS,
    ChapterFlashcards,
    ChapterQuestions,
    ContentSearch,
    KnowledgePack,
    SourceCatalog,
    SourceVerification,
    get_pack,
    list_pack_ids,
)
from knowledge_packs.packs import CybersecurityPack
from router_guard import manifest_scope_terms
from skills import ipas_cybersecurity
from skills.ipas_cybersecurity import IpasCybersecuritySkill, review
from skills.registry import DISCOVERY_RESULT

ROOT = Path(__file__).resolve().parents[1]
CYBER = ROOT / "skills" / "ipas_cybersecurity"
CAPABILITIES = (ChapterQuestions, SourceCatalog, ChapterFlashcards, ContentSearch, SourceVerification)


class ContractConformanceTest(unittest.TestCase):
    def test_registry_lists_the_three_packs_in_migration_order(self):
        self.assertEqual(list_pack_ids(), ("ipas_net_zero_planner", "ipas_ai_application_planner", "ipas_cybersecurity"))

    def test_every_pack_satisfies_the_required_contract(self):
        for pack_id in list_pack_ids():
            pack = get_pack(pack_id)
            with self.subTest(pack=pack_id):
                self.assertIsInstance(pack, KnowledgePack)
                self.assertEqual(pack.pack_id, pack_id)
                info = pack.get_course_info()
                self.assertLessEqual(set(COURSE_INFO_FIELDS), info.keys())
                self.assertEqual(info["skill_id"], pack_id)
                chapters = pack.get_chapters()
                self.assertEqual(info["chapter_count"], len(chapters))
                self.assertEqual(info["first_chapter_id"], chapters[0]["chapter_id"])
                for chapter in chapters:
                    self.assertEqual(pack.get_chapter(chapter["chapter_id"])["chapter_id"], chapter["chapter_id"])
                with self.assertRaises(ValueError):
                    pack.get_chapter("ch99" if pack_id == "ipas_net_zero_planner" else "NO-SUCH-CHAPTER")
                questions = pack.list_questions()
                self.assertTrue(questions)
                for question in questions:
                    self.assertLessEqual(set(QUESTION_FIELDS), question.keys())
                    self.assertFalse(set(HIDDEN_QUESTION_FIELDS) & question.keys())
                result = pack.submit_answer(questions[0]["question_id"], "A")
                self.assertLessEqual(set(GRADING_FIELDS), result.keys())
                with self.assertRaises(ValueError):
                    pack.submit_answer("NO-SUCH-Q999", "A")

    def test_unavailable_error_is_the_packs_own_class(self):
        for pack_id, module in (("ipas_net_zero_planner", main.ipas_net_zero_skill),
                                ("ipas_ai_application_planner", main.ipas_ai_skill),
                                ("ipas_cybersecurity", main.ipas_cyber_skill)):
            with self.subTest(pack=pack_id):
                self.assertIs(get_pack(pack_id).unavailable_error, module.DataUnavailableError)

    def test_optional_capabilities_exist_only_where_the_pack_has_the_feature(self):
        expected = {
            "ipas_net_zero_planner": {SourceCatalog, ContentSearch},
            "ipas_ai_application_planner": {SourceCatalog, ChapterQuestions},
            "ipas_cybersecurity": {SourceCatalog, ChapterQuestions, ChapterFlashcards, SourceVerification},
        }
        for pack_id, capabilities in expected.items():
            pack = get_pack(pack_id)
            with self.subTest(pack=pack_id):
                self.assertEqual({c for c in CAPABILITIES if isinstance(pack, c)}, capabilities)

    def test_adapters_pass_payloads_through_unchanged(self):
        for pack_id, module in (("ipas_net_zero_planner", main.ipas_net_zero_skill),
                                ("ipas_ai_application_planner", main.ipas_ai_skill),
                                ("ipas_cybersecurity", main.ipas_cyber_skill)):
            pack = get_pack(pack_id)
            with self.subTest(pack=pack_id):
                self.assertEqual(pack.get_course_info(), module.get_course_info())
                self.assertEqual(pack.get_chapters(), module.get_chapters())
                self.assertEqual(pack.get_sources(), module.get_sources())
                qid = pack.list_questions()[0]["question_id"]
                self.assertEqual(pack.submit_answer(qid, "B"), module.submit_answer(qid, "B"))
        self.assertEqual(get_pack("ipas_net_zero_planner").search("碳"), main.ipas_net_zero_skill.search("碳"))
        cyber = get_pack("ipas_cybersecurity")
        for chapter in cyber.get_chapters():
            self.assertEqual(cyber.get_flashcards(chapter["chapter_id"]), main.ipas_cyber_skill.get_flashcards(chapter["chapter_id"]))

    def test_list_questions_exposes_exactly_the_snapshot_questions_in_order(self):
        from tests.knowledge_pack_snapshot import FIXTURE

        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for pack_id in list_pack_ids():
            pack = get_pack(pack_id)
            with self.subTest(pack=pack_id):
                ids = [q["question_id"] for q in pack.list_questions()]
                self.assertEqual(ids, snapshot[pack_id]["question_ids"])
                if isinstance(pack, ChapterQuestions):
                    per_chapter = [q["question_id"] for c in pack.get_chapters()
                                   for q in pack.get_chapter_questions(c["chapter_id"])]
                    self.assertEqual(per_chapter, ids)

    def test_adapters_resolve_module_functions_at_call_time(self):
        with patch.object(main.ipas_ai_skill, "get_course_info", return_value={"patched": True}):
            self.assertEqual(get_pack("ipas_ai_application_planner").get_course_info(), {"patched": True})


class ChatRoutabilityIsNotAPackConcernTest(unittest.TestCase):
    def test_manifests_still_decide_chat_routability(self):
        manifests = {m.name: m for m in DISCOVERY_RESULT.manifests}
        self.assertEqual((manifests["ipas_net_zero_planner"].skill_type, manifests["ipas_net_zero_planner"].enabled), ("web", False))
        self.assertTrue(manifests["ipas_ai_application_planner"].enabled)
        self.assertTrue(manifests["ipas_cybersecurity"].enabled)
        self.assertEqual(len(manifest_scope_terms()), 67)
        self.assertFalse(hasattr(get_pack("ipas_net_zero_planner"), "answer"))


class CybersecuritySafeguardsTest(unittest.TestCase):
    def temp_pack(self, directory, *, ledger=None, manifest_sha=None):
        processed, cards = Path(directory) / "processed", Path(directory) / "cards"
        shutil.copytree(CYBER / "knowledge/processed", processed)
        shutil.copytree(CYBER / "cards", cards)
        if ledger is not None:
            (processed / "review_decisions.json").write_text(json.dumps(ledger), encoding="utf-8")
        if manifest_sha is not None:
            manifest = json.loads((processed / "source_manifest.json").read_text(encoding="utf-8"))
            manifest[0]["sha256"] = manifest_sha
            (processed / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        skill = IpasCybersecuritySkill(processed_dir=processed, cards_dir=cards)
        module = SimpleNamespace(DataUnavailableError=ipas_cybersecurity.DataUnavailableError,
                                 **{name: getattr(skill, name) for name in (
                                     "get_course_info", "get_chapters", "get_chapter", "get_questions",
                                     "get_flashcards", "submit_answer", "get_sources")})
        return CybersecurityPack(module), processed

    def test_source_verification_passes_on_the_canonical_pdf(self):
        get_pack("ipas_cybersecurity").verify_sources()

    def test_changed_source_hash_blocks_loading_and_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            pack, processed = self.temp_pack(directory, manifest_sha="0" * 64)
            with self.assertRaises(pack.unavailable_error):
                pack.get_course_info()
            with patch.object(review, "PROCESSED", processed), self.assertRaisesRegex(review.ReviewError, "hash changed"):
                get_pack("ipas_cybersecurity").verify_sources()

    def test_review_gate_hides_revised_content_through_the_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            pack, processed = self.temp_pack(directory, ledger=[])
            review.record_decision("chunk", "I11-ASSET-004", "revise", "Clarify scope", processed, Path(directory) / "cards")
            pack, _ = self.temp_pack(Path(directory) / "again", ledger=json.loads(
                (processed / "review_decisions.json").read_text(encoding="utf-8")))
            visible = {q["question_id"] for q in pack.list_questions()}
            self.assertNotIn("I11-ASSET-Q003", visible)
            self.assertIn("I11-CIA-Q001", visible)
            with self.assertRaises(ValueError):
                pack.submit_answer("I11-ASSET-Q003", "A")
            self.assertEqual(pack.get_chapter("I11-ASSET")["teaching_blocked_by"], ["I11-ASSET-004"])

    def test_pending_and_reviewed_states_and_citations_survive(self):
        pack = get_pack("ipas_cybersecurity")
        statuses = {q["question_id"].rsplit("-", 1)[0]: q["review_status"] for q in pack.list_questions()}
        self.assertEqual(statuses["I11-ASSET"], "reviewed")
        self.assertEqual(statuses["I11-PHYS"], "pending_review")
        result = pack.submit_answer("I11-PHYS-Q001", "A")
        self.assertEqual(result["source_references"][0]["source_pages"], [84])
        self.assertEqual(result["review_status"], "pending_review")
        self.assertEqual(pack.get_chapter("I11-CIA")["chunks"][0]["source_evidence"]["source_file"],
                         "iPAS_資訊安全管理概論_PART_I.pdf")


class FailureBehaviourTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_unavailable_data_keeps_existing_503_contracts(self):
        cases = (
            (main.ipas_ai_skill, "/api/ipas/answer", "IPAS-L111-Q001", "題庫暫時無法使用，請稍後再試。"),
            (main.ipas_net_zero_skill, "/api/ipas/net-zero-planner/answer", "NZ-Q001", "課程教材目前無法使用，請稍後再試。"),
            (main.ipas_cyber_skill, "/api/ipas/cybersecurity/answer", "I11-CIA-Q001", "資安教材目前無法使用。"),
        )
        for module, url, question_id, message in cases:
            with self.subTest(url=url), patch.object(module, "submit_answer", side_effect=module.DataUnavailableError("x")):
                response = self.client.post(url, json={"question_id": question_id, "answer": "A"})
                self.assertEqual((response.status_code, response.get_json()),
                                 (503, {"ok": False, "error": "skill_unavailable", "message": message}))

    def test_unexpected_errors_keep_existing_behaviour(self):
        for module, url, question_id, message in (
            (main.ipas_ai_skill, "/api/ipas/answer", "IPAS-L111-Q001", "批改失敗，請稍後再試。"),
            (main.ipas_net_zero_skill, "/api/ipas/net-zero-planner/answer", "NZ-Q001", "題目批改失敗，請稍後再試。"),
        ):
            with self.subTest(url=url), patch.object(module, "submit_answer", side_effect=RuntimeError("boom")):
                response = self.client.post(url, json={"question_id": question_id, "answer": "A"})
                self.assertEqual((response.status_code, response.get_json()),
                                 (500, {"ok": False, "error": "internal_error", "message": message}))
        # The cybersecurity answer route never had a generic handler: Flask's default 500 page.
        with patch.object(main.ipas_cyber_skill, "submit_answer", side_effect=RuntimeError("boom")):
            response = self.client.post("/api/ipas/cybersecurity/answer", json={"question_id": "I11-CIA-Q001", "answer": "A"})
        self.assertEqual(response.status_code, 500)
        self.assertIsNone(response.get_json(silent=True))

    def test_unavailable_pages_keep_existing_status_and_error_message(self):
        for module, url, attribute, message in (
            (main.ipas_ai_skill, "/ipas", "get_course_info", "課程教材暫時無法載入，請稍後再試。"),
            (main.ipas_net_zero_skill, "/ipas/net-zero-planner", "get_course_info", "淨零碳課程教材目前無法載入，請稍後再試。"),
            (main.ipas_cyber_skill, "/ipas/cybersecurity", "get_chapters", "資安教材目前無法載入。"),
        ):
            with self.subTest(url=url), patch.object(module, attribute, side_effect=module.DataUnavailableError("x")):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 503)
                self.assertIn(message, response.get_data(as_text=True))


class NoNetworkTest(unittest.TestCase):
    def test_pack_operations_make_no_external_network_attempts(self):
        before = list(tests.BLOCKED_NETWORK_ATTEMPTS)
        for pack_id in list_pack_ids():
            pack = get_pack(pack_id)
            pack.get_course_info()
            for question in pack.list_questions():
                pack.submit_answer(question["question_id"], "A")
        self.assertEqual(tests.BLOCKED_NETWORK_ATTEMPTS, before)


if __name__ == "__main__":
    unittest.main()
