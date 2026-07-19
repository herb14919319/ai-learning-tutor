import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from skills.discovery import (
    MANIFEST_FILENAME,
    ManifestValidationError,
    discover_skills,
    validate_manifest,
)
from skills.registry import (
    get_skill_metadata,
    list_skill_diagnostics,
    list_skill_manifests,
    list_skills,
)


def manifest_payload(skill_id: str, **overrides) -> dict:
    payload = {
        "schema_version": 1,
        "skill_id": skill_id,
        "display_name": skill_id.replace("_", " ").title(),
        "description": "Test skill",
        "status": "disabled",
        "skill_type": "runtime",
        "entrypoint": f"skills.{skill_id}",
        "priority": 10,
        "aliases": [],
        "domains": ["AI"],
        "keywords": ["LLM"],
        "capabilities": ["answer"],
    }
    payload.update(overrides)
    return payload


def add_manifest(root: Path, directory_name: str, payload: dict) -> Path:
    directory = root / directory_name
    directory.mkdir(parents=True)
    (directory / MANIFEST_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return directory


class ManifestValidationTest(unittest.TestCase):
    def test_valid_manifest_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_dir = add_manifest(root, "valid", manifest_payload("valid_skill"))
            manifest = validate_manifest(
                json.loads((skill_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")),
                skill_dir,
                root,
            )

        self.assertEqual(manifest.name, "valid_skill")
        self.assertEqual(manifest.status, "disabled")
        self.assertEqual(manifest.skill_type, "runtime")
        self.assertFalse(manifest.enabled)

    def test_invalid_schema_shapes_are_rejected_with_stable_codes(self):
        cases = (
            ({"skill_id": "missing_version"}, "unsupported_schema_version"),
            (manifest_payload("Bad-ID"), "invalid_skill_id"),
            (manifest_payload("bad_status", status="retired"), "invalid_status"),
            (manifest_payload("bad_type", skill_type="plugin"), "invalid_skill_type"),
            (manifest_payload("bad_priority", priority="high"), "invalid_priority"),
            (manifest_payload("missing_name", display_name=""), "missing_display_name"),
            (manifest_payload("unknown", surprise=True), "unknown_field"),
            (
                manifest_payload("bad_entrypoint", entrypoint="os.system"),
                "invalid_entrypoint",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_dir = root / "skill"
            skill_dir.mkdir()
            for payload, code in cases:
                with self.subTest(code=code), self.assertRaises(ManifestValidationError) as context:
                    validate_manifest(payload, skill_dir, root)
                self.assertEqual(context.exception.code, code)

    def test_content_paths_cannot_escape_or_be_absolute(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_dir = root / "skill"
            skill_dir.mkdir()
            payloads = (
                manifest_payload(
                    "traversal",
                    status="active",
                    skill_type="content",
                    entrypoint=None,
                    content_root="../outside",
                ),
                manifest_payload(
                    "absolute",
                    status="active",
                    skill_type="content",
                    entrypoint=None,
                    content_root=str(root.resolve()),
                ),
            )
            for payload in payloads:
                with self.assertRaises(ManifestValidationError) as context:
                    validate_manifest(payload, skill_dir, root)
                self.assertEqual(context.exception.code, "invalid_content_root")

    def test_missing_and_malformed_chapter_index_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_dir = root / "missing"
            (missing_dir / "content").mkdir(parents=True)
            missing = manifest_payload(
                "missing_index",
                status="active",
                skill_type="content",
                entrypoint=None,
                content_root="content",
                chapter_index="chapter_index.json",
            )
            with self.assertRaises(ManifestValidationError) as context:
                validate_manifest(missing, missing_dir, root)
            self.assertEqual(context.exception.code, "missing_chapter_index")

            malformed_dir = root / "malformed"
            content = malformed_dir / "content"
            content.mkdir(parents=True)
            (content / "chapter_index.json").write_text("{", encoding="utf-8")
            malformed = manifest_payload(
                "malformed_index",
                status="active",
                skill_type="content",
                entrypoint=None,
                content_root="content",
                chapter_index="chapter_index.json",
            )
            with self.assertRaises(ManifestValidationError) as context:
                validate_manifest(malformed, malformed_dir, root)
            self.assertEqual(context.exception.code, "malformed_chapter_index")


class SkillDiscoveryTest(unittest.TestCase):
    def test_discovery_is_sorted_and_loads_only_active_runtime_skills(self):
        runtime_module = SimpleNamespace(answer=lambda question: "answer")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_module.__file__ = str(root / "runtime.py")
            Path(runtime_module.__file__).write_text("", encoding="utf-8")
            add_manifest(
                root,
                "z-runtime",
                manifest_payload("runtime_skill", status="active"),
            )
            add_manifest(
                root,
                "a-disabled",
                manifest_payload("disabled_skill", status="disabled"),
            )
            add_manifest(
                root,
                "m-legacy",
                manifest_payload(
                    "legacy_skill",
                    status="disabled",
                    skill_type="legacy",
                    entrypoint="skills.legacy_skill",
                ),
            )
            with patch("skills.discovery.import_module", return_value=runtime_module) as importer:
                result = discover_skills(root)

        self.assertEqual(
            [manifest.name for manifest in result.manifests],
            ["disabled_skill", "legacy_skill", "runtime_skill"],
        )
        self.assertEqual(set(result.loaded_skills), {"runtime_skill"})
        importer.assert_called_once_with("skills.runtime_skill")

    def test_missing_and_malformed_manifests_do_not_block_valid_skill(self):
        runtime_module = SimpleNamespace(answer=lambda question: "answer")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_module.__file__ = str(root / "runtime.py")
            Path(runtime_module.__file__).write_text("", encoding="utf-8")
            (root / "no-manifest").mkdir()
            malformed = root / "malformed"
            malformed.mkdir()
            (malformed / MANIFEST_FILENAME).write_text("{", encoding="utf-8")
            add_manifest(
                root,
                "valid",
                manifest_payload("valid_skill", status="active"),
            )
            with patch("skills.discovery.import_module", return_value=runtime_module):
                result = discover_skills(root)

        self.assertIn("valid_skill", result.loaded_skills)
        self.assertEqual(result.unavailable["malformed"], "malformed_json")
        self.assertTrue(
            any(
                diagnostic.source == "no-manifest"
                and diagnostic.code == "manifest_missing"
                for diagnostic in result.diagnostics
            )
        )

    def test_duplicate_id_and_alias_are_handled_deterministically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_manifest(
                root,
                "a-first",
                manifest_payload("same_skill", aliases=["shared"]),
            )
            add_manifest(
                root,
                "b-duplicate-id",
                manifest_payload("same_skill", aliases=["different"]),
            )
            add_manifest(
                root,
                "c-duplicate-alias",
                manifest_payload("other_skill", aliases=["SHARED"]),
            )
            result = discover_skills(root)

        self.assertEqual([manifest.name for manifest in result.manifests], ["same_skill"])
        self.assertEqual(
            result.unavailable["same_skill@b-duplicate-id"],
            "duplicate_skill_id",
        )
        self.assertEqual(result.unavailable["other_skill"], "duplicate_alias")

    def test_import_failure_and_invalid_factory_result_are_isolated(self):
        valid_module = SimpleNamespace(answer=lambda question: "answer")
        invalid_factory_module = SimpleNamespace(create_skill=lambda: object())
        valid_factory_module = SimpleNamespace(
            create_skill=lambda: SimpleNamespace(answer=lambda question: "factory answer")
        )

        def fake_import(module_name):
            if module_name == "skills.broken":
                error = ModuleNotFoundError("missing entrypoint")
                error.name = module_name
                raise error
            if module_name == "skills.dependency":
                error = ModuleNotFoundError("missing dependency")
                error.name = "optional_dependency"
                raise error
            if module_name == "skills.invalid_factory":
                return invalid_factory_module
            if module_name == "skills.valid_factory":
                return valid_factory_module
            return valid_module

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_module.__file__ = str(root / "valid.py")
            invalid_factory_module.__file__ = str(root / "invalid_factory.py")
            valid_factory_module.__file__ = str(root / "valid_factory.py")
            Path(valid_module.__file__).write_text("", encoding="utf-8")
            Path(invalid_factory_module.__file__).write_text("", encoding="utf-8")
            Path(valid_factory_module.__file__).write_text("", encoding="utf-8")
            add_manifest(
                root,
                "a-broken",
                manifest_payload(
                    "broken",
                    status="active",
                    entrypoint="skills.broken",
                ),
            )
            add_manifest(
                root,
                "b-invalid",
                manifest_payload(
                    "invalid_factory",
                    status="active",
                    entrypoint="skills.invalid_factory:create_skill",
                ),
            )
            add_manifest(
                root,
                "c-valid",
                manifest_payload(
                    "valid",
                    status="active",
                    entrypoint="skills.valid",
                ),
            )
            add_manifest(
                root,
                "d-dependency",
                manifest_payload(
                    "dependency",
                    status="active",
                    entrypoint="skills.dependency",
                ),
            )
            add_manifest(
                root,
                "e-valid-factory",
                manifest_payload(
                    "valid_factory",
                    status="active",
                    entrypoint="skills.valid_factory:create_skill",
                ),
            )
            with patch("skills.discovery.import_module", side_effect=fake_import):
                result = discover_skills(root)

        self.assertEqual(set(result.loaded_skills), {"valid", "valid_factory"})
        self.assertEqual(result.unavailable["broken"], "entrypoint_not_found")
        self.assertEqual(result.unavailable["dependency"], "dependency_missing")
        self.assertEqual(result.unavailable["invalid_factory"], "invalid_runtime_object")
        self.assertFalse(
            next(manifest for manifest in result.manifests if manifest.name == "broken").enabled
        )

    def test_code_is_not_imported_before_manifest_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            add_manifest(
                root,
                "invalid",
                manifest_payload(
                    "invalid",
                    status="active",
                    entrypoint="skills.invalid",
                    surprise="not allowed",
                ),
            )
            with patch("skills.discovery.import_module") as importer:
                result = discover_skills(root)

        importer.assert_not_called()
        self.assertEqual(result.unavailable["invalid"], "unknown_field")

    def test_broken_content_package_does_not_block_runtime_skill(self):
        runtime_module = SimpleNamespace(answer=lambda question: "answer")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_module.__file__ = str(root / "runtime.py")
            Path(runtime_module.__file__).write_text("", encoding="utf-8")
            add_manifest(
                root,
                "broken-content",
                manifest_payload(
                    "broken_content",
                    status="active",
                    skill_type="content",
                    entrypoint=None,
                    content_root="missing",
                ),
            )
            add_manifest(
                root,
                "valid-runtime",
                manifest_payload("valid_runtime", status="active"),
            )
            with patch("skills.discovery.import_module", return_value=runtime_module):
                result = discover_skills(root)

        self.assertEqual(set(result.loaded_skills), {"valid_runtime"})
        self.assertEqual(result.unavailable["broken_content"], "missing_content")


class ExistingSkillMigrationTest(unittest.TestCase):
    def test_existing_runtime_ids_and_routing_metadata_are_preserved(self):
        active_ids = [metadata.name for metadata in list_skills()]
        self.assertEqual(
            active_ids,
            ["ipas_ai_application_planner", "hungyi_lee"],
        )
        hungyi = get_skill_metadata("hungyi_lee")
        ipas = get_skill_metadata("ipas_ai_application_planner")

        self.assertEqual(hungyi.entrypoint, "skills.hungyi_lee_skill")
        self.assertIn("AI", hungyi.domains)
        self.assertIn("Transformer", hungyi.keywords)
        self.assertEqual(ipas.entrypoint, "skills.ipas_ai_application_planner")
        self.assertIn("L111", ipas.keywords)

    def test_non_runtime_and_legacy_packages_are_classified_but_not_routed(self):
        manifests = {manifest.name: manifest for manifest in list_skill_manifests()}

        self.assertEqual(manifests["fa"].skill_type, "web")
        self.assertEqual(manifests["ipas_net_zero_planner"].skill_type, "web")
        self.assertEqual(manifests["little_tree"].skill_type, "web")
        self.assertEqual(manifests["little_tree_companion"].skill_type, "legacy")
        self.assertFalse(manifests["little_tree_companion"].enabled)
        self.assertNotIn("fa", [metadata.name for metadata in list_skills()])
        self.assertNotIn("ipas_net_zero_planner", [metadata.name for metadata in list_skills()])
        self.assertNotIn("little_tree", [metadata.name for metadata in list_skills()])

    def test_startup_diagnostics_do_not_expose_absolute_repository_paths(self):
        serialized = json.dumps(
            [diagnostic.__dict__ for diagnostic in list_skill_diagnostics()],
            ensure_ascii=False,
        )

        self.assertNotIn(str(Path.cwd().resolve()), serialized)


if __name__ == "__main__":
    unittest.main()
