from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.ipas_ai_application_planner.skill import IpasAiApplicationPlannerSkill
from skills.ipas_ai_application_planner.scripts import process_sources


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "skills" / "ipas_ai_application_planner" / "knowledge" / "processed"
SOURCE = ROOT / "skills" / "ipas_ai_application_planner" / "knowledge" / "source"
INDEX_PATH = PROCESSED / "chapter_index.json"
REQUIRED_FIELDS = {"chapter_id", "lesson_code", "title", "order", "source_file", "status"}
EXPECTED_MAPPING = [
    ("CH-01", "L111", 1, "ch01_ai_concepts.md"),
    ("CH-02", "L112", 2, "ch02_data_processing_and_analysis.md"),
    ("CH-03", "L113", 3, "ch03_machine_learning_concepts.md"),
    ("CH-04", "L114", 4, "ch04_discriminative_and_generative_ai_concepts.md"),
    ("CH-05", "L121", 5, "ch05_no_code_low_code_concepts.md"),
    ("CH-06", "L122", 6, "ch06_generative_ai_applications_and_tools.md"),
    ("CH-07", "L123", 7, "ch07_generative_ai_adoption_evaluation_and_planning.md"),
]


def copy_formal_course(target: Path, *, include_index: bool = True) -> None:
    current = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    for item in current:
        shutil.copy2(PROCESSED / item["source_file"], target / item["source_file"])
    if include_index:
        shutil.copy2(INDEX_PATH, target / "chapter_index.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IpasProcessSourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.processed_copy = tempfile.TemporaryDirectory()
        cls.output = Path(cls.processed_copy.name)
        copy_formal_course(cls.output)
        cls.markdown_hashes_before = {
            path.name: sha256(path) for path in cls.output.glob("ch*.md")
        }
        process_sources.process(SOURCE, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.processed_copy.cleanup()

    def test_build_chapter_index_produces_seven_formal_chapters(self):
        chapters = process_sources.build_chapter_index(self.output)

        self.assertEqual(len(chapters), 7)
        self.assertEqual(
            [(item["chapter_id"], item["lesson_code"], item["order"], item["source_file"]) for item in chapters],
            EXPECTED_MAPPING,
        )

    def test_generated_schema_has_required_fields_and_no_legacy_fields(self):
        chapters = process_sources.build_chapter_index(self.output)

        for chapter in chapters:
            with self.subTest(chapter_id=chapter["chapter_id"]):
                self.assertTrue(REQUIRED_FIELDS <= chapter.keys())
                self.assertNotIn("topic_code", chapter)
                self.assertNotIn("processing_status", chapter)
                self.assertNotIn("indexed_only", chapter.values())

    def test_all_sources_exist_and_statuses_are_completed(self):
        chapters = process_sources.build_chapter_index(self.output)

        self.assertTrue(all(item["status"] == "completed" for item in chapters))
        self.assertTrue(all((self.output / item["source_file"]).is_file() for item in chapters))

    def test_generated_index_semantically_matches_current_formal_index(self):
        current = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        generated = process_sources.build_chapter_index(self.output)

        self.assertEqual(generated, current)

    def test_rerun_output_passes_skill_schema_and_loads_all_questions(self):
        skill = IpasAiApplicationPlannerSkill(self.output)
        chapters = skill.get_chapters()

        self.assertEqual(len(chapters), 7)
        self.assertEqual([item["question_count"] for item in chapters], [8] * 7)
        self.assertEqual(len(skill.get_questions()), 56)

    def test_process_keeps_legacy_outputs_without_modifying_markdown(self):
        self.assertTrue((self.output / "source_manifest.json").is_file())
        self.assertEqual(len(json.loads((self.output / "l111_knowledge.json").read_text(encoding="utf-8"))), 10)
        self.assertEqual(len(json.loads((self.output / "l111_questions.json").read_text(encoding="utf-8"))), 10)
        hashes_after = {path.name: sha256(path) for path in self.output.glob("ch*.md")}
        self.assertEqual(hashes_after, self.markdown_hashes_before)

    def test_missing_markdown_refuses_to_overwrite_valid_index(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            copy_formal_course(target)
            index = target / "chapter_index.json"
            original = index.read_bytes()
            (target / "ch04_discriminative_and_generative_ai_concepts.md").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "CH-04.*未覆寫既有索引"):
                chapters = process_sources.build_chapter_index(target)
                process_sources.write_chapter_index(index, chapters, target)

            self.assertEqual(index.read_bytes(), original)

    def test_duplicate_identity_fields_are_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            copy_formal_course(target)
            index = target / "chapter_index.json"
            original = index.read_bytes()
            for field in ("chapter_id", "lesson_code", "order", "source_file"):
                with self.subTest(field=field):
                    payload = process_sources.build_chapter_index(target)
                    payload[1][field] = payload[0][field]
                    with self.assertRaisesRegex(ValueError, rf"{field} 不可重複"):
                        process_sources.write_chapter_index(index, payload, target)
                    self.assertEqual(index.read_bytes(), original)

    def test_non_completed_or_legacy_schema_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            copy_formal_course(target)
            index = target / "chapter_index.json"
            original = index.read_bytes()

            payload = process_sources.build_chapter_index(target)
            payload[2]["status"] = "indexed_only"
            with self.assertRaisesRegex(ValueError, "status 必須為 completed"):
                process_sources.write_chapter_index(index, payload, target)
            self.assertEqual(index.read_bytes(), original)

            payload = process_sources.build_chapter_index(target)
            payload[0]["processing_status"] = "processed_mvp"
            with self.assertRaisesRegex(ValueError, "包含舊欄位"):
                process_sources.write_chapter_index(index, payload, target)
            self.assertEqual(index.read_bytes(), original)

    def test_atomic_replace_failure_preserves_original_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            copy_formal_course(target)
            index = target / "chapter_index.json"
            original = index.read_bytes()
            payload = process_sources.build_chapter_index(target)

            with patch.object(process_sources.os, "replace", side_effect=OSError("simulated replace failure")):
                with self.assertRaisesRegex(OSError, "simulated replace failure"):
                    process_sources.write_chapter_index(index, payload, target)

            self.assertEqual(index.read_bytes(), original)
            self.assertEqual(list(target.glob(".chapter_index.json.*.tmp")), [])

    def test_atomic_writer_flushes_and_fsyncs_before_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "payload.json"
            with (
                patch.object(process_sources.os, "fsync", wraps=process_sources.os.fsync) as fsync,
                patch.object(process_sources.os, "replace", wraps=process_sources.os.replace) as replace,
            ):
                process_sources.write_json(target, {"ok": True})

            self.assertTrue(fsync.called)
            self.assertTrue(replace.called)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_legacy_write_failure_leaves_existing_chapter_index_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            copy_formal_course(target)
            index = target / "chapter_index.json"
            original = index.read_bytes()
            real_write_json = process_sources.write_json

            def fail_on_questions(path: Path, payload: object) -> None:
                if Path(path).name == "l111_questions.json":
                    raise OSError("simulated legacy write failure")
                real_write_json(path, payload)

            with patch.object(process_sources, "write_json", side_effect=fail_on_questions):
                with self.assertRaisesRegex(OSError, "simulated legacy write failure"):
                    process_sources.process(SOURCE, target)

            self.assertEqual(index.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
