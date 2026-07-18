# Skill Manifest and Safe Auto-Discovery Contract

## 1. Purpose

This contract makes Runtime Skill onboarding deterministic, reviewable, and fail-isolated. A new Runtime Skill can be introduced with a direct child directory, a validated `skill.json`, and a local Python entrypoint without editing the central registry, Tutor Agent, or router.

The contract is deliberately smaller than a plugin framework. It covers repository-local metadata, discovery, validation, loading, registry projection, diagnostics, and compatibility.

## 2. Scope

Discovery scans direct child directories of the configured `skills/` root for one fixed filename:

```text
skill.json
```

It classifies all manifest-bearing packages but auto-loads only active Runtime Skills. Flask routes, templates, navigation, grading endpoints, content generation, and remote package installation remain explicit systems.

## 3. Skill Classification

`skill_type` has five allowed values:

| Type | Meaning | Auto-loaded into Tutor Runtime |
| --- | --- | --- |
| `runtime` | Routes, selects, and answers a Tutor request | Only when `status` is `active` |
| `content` | Markdown, indexes, cards, or source metadata | No |
| `deterministic` | Grading, browsing, lookup, or search tooling | No |
| `web` | Dedicated Flask/template/JavaScript application | No |
| `legacy` | Retained compatibility path that must not auto-activate | No |

Current classifications:

- `hungyi_lee`: active Runtime Skill with a local wiki content root.
- `ipas_ai_application_planner`: active Runtime Skill that also has explicitly wired course pages.
- `fa`: dedicated Web package.
- `ipas_net_zero_planner`: dedicated Web package with deterministic tools.
- `little_tree_companion`: disabled legacy package; its active-state compatibility path remains unchanged.

## 4. Manifest Schema

The manifest is UTF-8 JSON:

```json
{
  "schema_version": 1,
  "skill_id": "ai_course",
  "display_name": "AI Course",
  "description": "AI course tutoring.",
  "status": "active",
  "skill_type": "runtime",
  "entrypoint": "skills.ai_course.skill:create_skill",
  "priority": 100,
  "aliases": ["ai course"],
  "domains": ["AI"],
  "keywords": ["Transformer"],
  "capabilities": ["qa"],
  "content_root": "content",
  "chapter_index": "chapter_index.json"
}
```

Schema version `1` is the only supported version. Unknown fields are rejected rather than silently ignored, preventing misspelled security- or routing-sensitive configuration.

## 5. Field Definitions

Required for every manifest:

| Field | Type | Rule |
| --- | --- | --- |
| `schema_version` | integer | Must be `1` |
| `skill_id` | string | Matches `^[a-z][a-z0-9_]{1,63}$` |
| `display_name` | string | Non-empty label |
| `status` | string | `active`, `disabled`, or `experimental` |
| `skill_type` | string | One classification from section 3 |

Runtime Skills additionally require `entrypoint`.

Optional fields:

- `description`: non-empty string when present.
- `priority`: integer, default `0`; booleans are rejected.
- `aliases`, `domains`, `keywords`, `capabilities`: arrays of non-empty strings.
- `content_root`: safe relative directory below the Skill directory.
- `chapter_index`: safe relative JSON file below `content_root`.

`entrypoint` is either a repository-local module (`skills.example.skill`) or a zero-argument factory (`skills.example.skill:create_skill`).

## 6. Discovery Lifecycle

```text
configured skills root
→ enumerate direct child directories
→ exclude hidden/internal directories
→ sort directory names case-insensitively
→ locate skill.json
→ parse JSON without importing Skill code
→ validate schema, enums, entrypoint, and paths
→ reserve Skill ID and aliases
→ classify package
→ import only active Runtime Skills
→ validate module/factory result
→ create ModuleSkillAdapter
→ project catalog, runtime cache, unavailable map, and diagnostics
```

No recursive filesystem scan is used. Directory names never determine Skill IDs or routing order.

## 7. Runtime Interface

The compatibility interface remains intentionally small:

```python
def answer(question: str) -> str:
    ...
```

An optional `configure(ask_gpt)` callback may be present. A module entrypoint can expose these functions directly. A factory entrypoint must return an object with callable `answer`.

`ModuleSkillAdapter` supplies the existing `SkillContract` behavior to `SkillRuntime`. The manifest owns `skill_id`; another framework-level base class is unnecessary.

## 8. Registry Responsibilities

`skills/registry.py` is now a projection rather than the metadata source of truth. It owns:

- configured-root discovery;
- `SkillCatalog` creation;
- preloaded Runtime adapters;
- existing APIs such as `list_skills()`, `get_skill()`, and `get_runtime()`;
- read-only manifest, unavailable, and diagnostic projections.

It does not own routing keywords, prompt assembly, provider selection, Flask routes, or course content.

`SKILL_MANIFESTS` remains as a backward-compatible projection of validated manifests; it is no longer a hand-maintained tuple.

## 9. Error Isolation

Every directory is processed independently. Stable diagnostics include:

- `manifest_missing`, `malformed_json`, `manifest_unreadable`
- `unknown_field`, `unsupported_schema_version`
- `invalid_skill_id`, `invalid_status`, `invalid_skill_type`, `invalid_entrypoint`
- `duplicate_skill_id`, `duplicate_alias`
- `missing_content`, `missing_chapter_index`, `malformed_chapter_index`
- `entrypoint_not_found`, `dependency_missing`
- `invalid_factory`, `invalid_runtime_object`, `unsafe_entrypoint`
- `runtime_load_failed`

An unavailable Skill is disabled in the registry projection while other valid Skills continue loading. Runtime failures are logged with Skill ID and stable reason without exposing exception text through diagnostics.

## 10. Duplicate Handling

Directories are processed in deterministic sorted order.

- The first validated `skill_id` claims the ID.
- A later duplicate receives `duplicate_skill_id`.
- Aliases are compared case-insensitively.
- The first alias owner wins; later duplicates receive `duplicate_alias`.
- A duplicate never overwrites an earlier manifest or adapter.

Domains and keywords may overlap intentionally because priority defines routing precedence. Alias uniqueness is stricter because aliases represent package identity.

## 11. Security Boundaries

Discovery:

- never executes or evaluates manifest data;
- never downloads code or follows HTTP entrypoints;
- rejects absolute paths and `..` traversal;
- resolves content and index paths below declared boundaries;
- rejects linked directories or paths escaping the configured root;
- accepts only `skills.*` Python entrypoints;
- verifies imported module files are physically below the configured `skills/` root;
- imports only after complete manifest and content-path validation;
- imports only active Runtime Skills;
- excludes secrets, prompts, course content, exception messages, and absolute repository paths from diagnostics.

Manifests are trusted repository configuration reviewed through source control, not an upload or remote-install format.

## 12. Routing Compatibility

Validated `domains`, `keywords`, `aliases`, and `priority` are projected into existing `SkillMetadata`.

Routing behavior remains:

- enabled Runtime Skills are ordered by descending priority;
- the first metadata match wins with reason `metadata_match`;
- unmatched requests use `general`;
- disabled, experimental, Web, content, deterministic, unavailable, and legacy packages never route.

Existing Skill IDs, priorities, capabilities, entrypoints, and routing terms are preserved. Provider selection and request-correlation telemetry are unchanged.

## 13. Content Compatibility

`content_root` and `chapter_index` provide safe existence and JSON-readability checks only. Discovery does not impose one chapter schema across courses.

If either declared path is missing, unsafe, unreadable, or malformed, only that package becomes unavailable. Existing iPAS loaders remain responsible for course-specific chapter, question, title, and source validation.

Discovery never regenerates or rewrites content, indexes, Markdown, cards, or processing-script output.

## 14. Legacy Migration

Existing active Runtime Skills now carry manifests:

- `skills/hung-yi-lee-skill/skill.json`
- `skills/ipas_ai_application_planner/skill.json`

Non-runtime packages also carry classification manifests so they cannot be mistaken for Tutor Runtime Skills.

Little Tree uses a disabled `legacy` manifest under `skills/legacy_little_tree/`. Discovery records it but never imports or activates it. Existing legacy imports and active-state behavior remain unchanged pending a separate removal decision.

No hard-coded Runtime fallback remains. A Runtime directory without a manifest is diagnosed and ignored, leaving one metadata source of truth.

## 15. Diagnostics

The registry exposes:

- `list_skill_manifests()`
- `list_unavailable_skills()`
- `list_skill_diagnostics()`

Diagnostics contain only source directory name, optional Skill ID, stable code, and outcome. They are startup diagnostics and do not receive a user request ID.

If a request reaches a previously selected unavailable Skill, existing Tutor behavior records its Skill ID, emits `skill_unavailable`, and falls back to the general route under the request telemetry ID.

## 16. Tests

Contract tests cover validation, path security, content isolation, deterministic ordering, disabled/legacy behavior, duplicate handling, import/factory isolation, proof that invalid manifests are not imported, existing routing metadata, and diagnostics privacy. The complete application regression suite protects channel, API, provider, telemetry, iPAS, and FA behavior.

## 17. Deferred Work

- Generic Flask route and UI navigation registration.
- Deterministic tool registration.
- Cross-course chapter/content schemas.
- Little Tree code removal.
- Hot reload and filesystem watching.
- Remote registries or package installation.
- Cross-process lifecycle management.

## 18. Non-Goals

This change does not add a plugin manager, hooks, an event bus, dependency-injection container, database, Redis, queue, vector database, RAG system, provider, remote download, or hot reload.

It does not rewrite `main.py`, Router Guard, provider fallback, telemetry schema, prompts, UI routes, course content, chapter indexes, or processing scripts. It does not treat every directory under `skills/` as executable Runtime code.
