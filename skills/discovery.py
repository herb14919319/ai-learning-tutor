from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from skills.adapters import ModuleSkillAdapter
from skills.runtime import SkillManifest


logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "skill.json"
SUPPORTED_SCHEMA_VERSION = 1
ALLOWED_STATUSES = {"active", "disabled", "experimental"}
ALLOWED_SKILL_TYPES = {"runtime", "content", "deterministic", "web", "legacy"}
ALLOWED_FIELDS = {
    "schema_version",
    "skill_id",
    "display_name",
    "description",
    "status",
    "skill_type",
    "entrypoint",
    "priority",
    "aliases",
    "domains",
    "keywords",
    "capabilities",
    "content_root",
    "chapter_index",
}
SKILL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ENTRYPOINT_PATTERN = re.compile(
    r"^skills(?:\.[A-Za-z_][A-Za-z0-9_]*)+(?::[A-Za-z_][A-Za-z0-9_]*)?$"
)


@dataclass(frozen=True)
class SkillDiagnostic:
    source: str
    code: str
    outcome: str
    skill_id: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    manifests: tuple[SkillManifest, ...]
    loaded_skills: dict[str, ModuleSkillAdapter]
    unavailable: dict[str, str]
    diagnostics: tuple[SkillDiagnostic, ...]


class ManifestValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class RuntimeSkillLoadError(TypeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def discover_skills(skills_root: Path) -> DiscoveryResult:
    root = Path(skills_root).resolve()
    manifests: list[SkillManifest] = []
    loaded_skills: dict[str, ModuleSkillAdapter] = {}
    unavailable: dict[str, str] = {}
    diagnostics: list[SkillDiagnostic] = []
    claimed_ids: set[str] = set()
    claimed_aliases: dict[str, str] = {}

    try:
        directories = sorted(
            (
                child
                for child in root.iterdir()
                if child.is_dir() and not child.name.startswith((".", "_"))
            ),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        logger.exception("Skill discovery root could not be enumerated")
        return DiscoveryResult((), {}, {"registry": "discovery_root_unavailable"}, ())

    for directory in directories:
        source = directory.name
        manifest_path = directory / MANIFEST_FILENAME
        try:
            directory.resolve().relative_to(root)
            manifest_path.resolve().relative_to(root)
        except ValueError:
            unavailable[source] = "unsafe_skill_directory"
            diagnostics.append(
                SkillDiagnostic(source, "unsafe_skill_directory", "unavailable")
            )
            continue
        if not manifest_path.is_file():
            diagnostics.append(SkillDiagnostic(source, "manifest_missing", "ignored"))
            continue

        raw_skill_id: str | None = None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("skill_id"), str):
                raw_skill_id = payload["skill_id"]
            manifest = validate_manifest(payload, directory, root)
        except json.JSONDecodeError:
            code = "malformed_json"
            unavailable[source] = code
            diagnostics.append(SkillDiagnostic(source, code, "unavailable", raw_skill_id))
            continue
        except (OSError, UnicodeError):
            code = "manifest_unreadable"
            unavailable[source] = code
            diagnostics.append(SkillDiagnostic(source, code, "unavailable", raw_skill_id))
            continue
        except ManifestValidationError as exc:
            unavailable[raw_skill_id or source] = exc.code
            diagnostics.append(
                SkillDiagnostic(source, exc.code, "unavailable", raw_skill_id)
            )
            continue

        if manifest.name in claimed_ids:
            code = "duplicate_skill_id"
            unavailable[f"{manifest.name}@{source}"] = code
            diagnostics.append(
                SkillDiagnostic(source, code, "unavailable", manifest.name)
            )
            continue

        duplicate_alias = next(
            (
                alias
                for alias in manifest.aliases
                if alias.casefold() in claimed_aliases
            ),
            None,
        )
        if duplicate_alias is not None:
            code = "duplicate_alias"
            unavailable[manifest.name] = code
            diagnostics.append(
                SkillDiagnostic(source, code, "unavailable", manifest.name)
            )
            continue

        claimed_ids.add(manifest.name)
        for alias in manifest.aliases:
            claimed_aliases[alias.casefold()] = manifest.name
        manifests.append(manifest)

        if manifest.status != "active":
            diagnostics.append(
                SkillDiagnostic(source, manifest.status, manifest.status, manifest.name)
            )
            continue
        if manifest.skill_type != "runtime":
            diagnostics.append(
                SkillDiagnostic(source, "classified_non_runtime", "discovered", manifest.name)
            )
            continue

        try:
            adapter = load_runtime_skill(manifest, root)
        except ModuleNotFoundError as exc:
            module_name = manifest.entrypoint.partition(":")[0]
            code = "entrypoint_not_found" if exc.name == module_name else "dependency_missing"
            unavailable[manifest.name] = code
            diagnostics.append(
                SkillDiagnostic(source, code, "unavailable", manifest.name)
            )
            continue
        except ImportError:
            code = "dependency_missing"
            unavailable[manifest.name] = code
            diagnostics.append(
                SkillDiagnostic(source, code, "unavailable", manifest.name)
            )
            continue
        except AttributeError:
            code = "entrypoint_not_found"
            unavailable[manifest.name] = code
            diagnostics.append(
                SkillDiagnostic(source, code, "unavailable", manifest.name)
            )
            continue
        except RuntimeSkillLoadError as exc:
            unavailable[manifest.name] = exc.code
            diagnostics.append(
                SkillDiagnostic(source, exc.code, "unavailable", manifest.name)
            )
            continue
        except Exception:
            code = "runtime_load_failed"
            unavailable[manifest.name] = code
            diagnostics.append(
                SkillDiagnostic(source, code, "unavailable", manifest.name)
            )
            logger.warning(
                "Skill runtime load failed skill_id=%s reason=%s",
                manifest.name,
                code,
            )
            continue

        loaded_skills[manifest.name] = adapter
        diagnostics.append(SkillDiagnostic(source, "loaded", "loaded", manifest.name))

    projected_manifests = tuple(
        replace(
            manifest,
            enabled=manifest.enabled and manifest.name not in unavailable,
        )
        for manifest in manifests
    )
    return DiscoveryResult(
        manifests=projected_manifests,
        loaded_skills=loaded_skills,
        unavailable=unavailable,
        diagnostics=tuple(diagnostics),
    )


def validate_manifest(
    payload: Any,
    skill_directory: Path,
    skills_root: Path,
) -> SkillManifest:
    if not isinstance(payload, dict):
        raise ManifestValidationError("manifest_not_object")
    unknown_fields = set(payload) - ALLOWED_FIELDS
    if unknown_fields:
        raise ManifestValidationError("unknown_field")
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ManifestValidationError("unsupported_schema_version")

    skill_id = required_string(payload, "skill_id")
    if not SKILL_ID_PATTERN.fullmatch(skill_id):
        raise ManifestValidationError("invalid_skill_id")
    display_name = required_string(payload, "display_name")
    status = required_string(payload, "status")
    if status not in ALLOWED_STATUSES:
        raise ManifestValidationError("invalid_status")
    skill_type = required_string(payload, "skill_type")
    if skill_type not in ALLOWED_SKILL_TYPES:
        raise ManifestValidationError("invalid_skill_type")

    description = optional_string(payload, "description") or ""
    priority = payload.get("priority", 0)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ManifestValidationError("invalid_priority")

    aliases = string_tuple(payload, "aliases")
    domains = string_tuple(payload, "domains")
    keywords = string_tuple(payload, "keywords")
    capabilities = string_tuple(payload, "capabilities")
    if len({alias.casefold() for alias in aliases}) != len(aliases):
        raise ManifestValidationError("duplicate_alias")

    entrypoint = optional_string(payload, "entrypoint") or ""
    if skill_type == "runtime" and not entrypoint:
        raise ManifestValidationError("missing_entrypoint")
    if entrypoint and not ENTRYPOINT_PATTERN.fullmatch(entrypoint):
        raise ManifestValidationError("invalid_entrypoint")

    content_root = optional_string(payload, "content_root")
    chapter_index = optional_string(payload, "chapter_index")
    resolved_content_root: Path | None = None
    if content_root:
        resolved_content_root = safe_relative_path(
            skill_directory,
            content_root,
            skills_root,
            "invalid_content_root",
        )
        if not resolved_content_root.is_dir():
            raise ManifestValidationError("missing_content")
    if chapter_index:
        if resolved_content_root is None:
            raise ManifestValidationError("chapter_index_without_content_root")
        index_path = safe_relative_path(
            resolved_content_root,
            chapter_index,
            skill_directory,
            "invalid_chapter_index_path",
        )
        if not index_path.is_file():
            raise ManifestValidationError("missing_chapter_index")
        try:
            json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestValidationError("malformed_chapter_index") from exc
        except (OSError, UnicodeError) as exc:
            raise ManifestValidationError("chapter_index_unreadable") from exc

    enabled = status == "active" and skill_type == "runtime"
    return SkillManifest(
        name=skill_id,
        display_name=display_name,
        description=description,
        domains=domains,
        keywords=keywords + aliases,
        capabilities=capabilities,
        entrypoint=entrypoint,
        priority=priority,
        enabled=enabled,
        status=status,
        skill_type=skill_type,
        aliases=aliases,
        content_root=content_root,
        chapter_index=chapter_index,
        source=skill_directory.name,
    )


def load_runtime_skill(
    manifest: SkillManifest,
    skills_root: Path,
) -> ModuleSkillAdapter:
    module_name, separator, attribute = manifest.entrypoint.partition(":")
    module = import_module(module_name)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise RuntimeSkillLoadError("unsafe_entrypoint")
    module_path = Path(module_file).resolve()
    try:
        module_path.relative_to(Path(skills_root).resolve())
    except ValueError as exc:
        raise RuntimeSkillLoadError("unsafe_entrypoint") from exc
    if not module_path.is_file():
        raise RuntimeSkillLoadError("unsafe_entrypoint")
    target: Any = module
    if separator:
        factory = getattr(module, attribute)
        if not callable(factory):
            raise RuntimeSkillLoadError("invalid_factory")
        target = factory()
    if not callable(getattr(target, "answer", None)):
        raise RuntimeSkillLoadError("invalid_runtime_object")
    return ModuleSkillAdapter(target, manifest.to_metadata())


def required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"missing_{field}")
    return value.strip()


def optional_string(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"invalid_{field}")
    return value.strip()


def string_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value = payload.get(field, [])
    if not isinstance(value, list):
        raise ManifestValidationError(f"invalid_{field}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ManifestValidationError(f"invalid_{field}")
    return tuple(item.strip() for item in value)


def safe_relative_path(
    base: Path,
    value: str,
    boundary: Path,
    error_code: str,
) -> Path:
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    ):
        raise ManifestValidationError(error_code)
    candidate = (base / value).resolve()
    try:
        candidate.relative_to(Path(boundary).resolve())
    except ValueError as exc:
        raise ManifestValidationError(error_code) from exc
    return candidate
