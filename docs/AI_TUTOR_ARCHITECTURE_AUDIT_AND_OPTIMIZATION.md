# AI Learning Tutor Architecture Audit and Convergent Optimization

Audit date: 2026-07-18  
Repository revision audited: `d0a236c` (`main`)  
Verdict: **NEEDS STABILIZATION**

## 1. Executive Summary

The repository has a real shared tutor core, deterministic learning boundary, lazy skill runtime, bounded in-memory context, provider clients, and a useful test suite. It is more than a collection of unrelated course applications. However, it is not yet a plug-in-style learning platform: enabled chat skills are declared in a Python tuple, the two iPAS course applications use different data contracts, the net-zero course bypasses the generic Tutor skill registry, and important route/guard/skill decisions are absent from telemetry.

The audit found five P0 issues and six P1 issues. All P0 issues and two P1 issues were selected:

- Public Web Chat put every visitor into the same `web-demo` context.
- `POST /api/agent/ask` could call the model without authentication, request-size control, question-length control, or rate limiting.
- `GET /test` could call the model without the controls used by the external Tutor API.
- Messenger accepted unsigned webhook POSTs.
- Messenger webhook retries could enqueue and push the same answer more than once.
- DeepSeek had no fallback, and Gemini fallback covered only HTTP 429.
- Public Web Chat had no question-length or request-rate boundary.

The fixes are deliberately local. They reuse existing API-key/rate-limit functions, keep public Web Chat stateless until it has authenticated identity, verify Messenger's HMAC-SHA256 signature, add process-local Messenger `mid` deduplication consistent with the one-worker deployment, and allow only retryable Gemini/DeepSeek failures to fall back once to OpenAI.

The full suite passed: **229 tests, 0 failures, 0 errors**.

## 2. Current Architecture Map

### Repository map

| Area | Actual implementation |
|---|---|
| Composition and HTTP entry points | `main.py` |
| LINE | `main.py`, `menu_router.py`, LINE SDK |
| Messenger | `messenger_webhook.py`, `messenger_client.py` |
| Tutor orchestration | `agents/tutor_agent.py` |
| Product boundary guard | `router_guard.py` |
| Active skill routing/loading | `skills/runtime.py`, `skills/registry.py`, `skills/adapters.py` |
| Provider clients and entrypoint policy | `models/clients.py`, `models/routing.py` |
| Conversation state | `memory/conversation_context.py` |
| Runtime telemetry/dashboard | `runtime_telemetry.py`, `templates/runtime_observability.html` |
| iPAS AI Application Planner | `skills/ipas_ai_application_planner/` plus direct routes in `main.py` |
| iPAS Net-Zero Planner | `skills/ipas_net_zero_planner/` plus direct routes in `main.py` |
| Hung-Yi Lee knowledge skill | `skills/hungyi_lee_skill.py`, `skills/hung-yi-lee-skill/` |
| FA assistant | `skills/fa/`, explicit `skill_id=fa` Web Chat branch |
| Legacy Little Tree | `agents/little_tree*`, `skills/little_tree_companion.py`, residual wiring in `main.py` |
| Tests | `tests/`, standard-library `unittest` |
| Deployment | `Dockerfile`: Gunicorn, one worker, eight threads |

No nested Git repository was found. The initial worktree was clean. `.env` is ignored as expected; formal Skill material, processed chapter indexes, images, and `data/runtime_telemetry.jsonl` are tracked. No untracked runtime dependency was found.

`agents/router.py` is a duplicate router used only by tests. Production `TutorAgent` calls `SkillRuntime.route()` instead.

### Runtime responsibility map

```text
channel/API adapter
  -> channel validation and normalization
  -> generate_tutor_answer()
  -> Little Tree legacy-state check
  -> deterministic Router Guard
  -> TutorAgent.answer()
  -> SkillRuntime metadata route
  -> lazy skill import + adapter
  -> local retrieval/deterministic course logic and/or model call
  -> provider telemetry
  -> channel return or background push
```

The two iPAS course web applications and FA branch are exceptions. They are direct routes to their respective Python modules and do not all pass through `SkillRuntime`.

## 3. Request Lifecycle

### LINE: `POST /callback`

1. `main.callback()` reads the body and `X-Line-Signature`.
2. LINE SDK `WebhookHandler.handle()` verifies the signature.
3. `handle_text_message()` deduplicates webhook event/message ID.
4. Rich Menu commands return deterministic text/image without the Tutor runtime.
5. Other messages receive the immediate processing reply.
6. A background executor calls `process_text_message_async()`.
7. `/help` returns deterministic help; other messages call `generate_tutor_reply()`.
8. The 45-second wrapper calls `generate_ai_reply()` with entrypoint `line`.
9. Shared core runs Guard, Skill routing, context, prompt, provider, fallback, and provider-call telemetry.
10. The final answer or fallback is pushed once.

Identity is the LINE user ID when present, otherwise group/room ID. There is process-local event deduplication. There is no application-level LINE question-length or rate limiter; LINE signature validation and platform message limits reduce, but do not eliminate, that exposure.

### Web Chat: `POST /web-chat`

1. JSON and `message` are normalized.
2. Empty and over-3,000-character questions are rejected.
3. The existing process-local IP rate limiter runs.
4. `skill_id=fa` uses the explicit deterministic FA flow.
5. General Web Chat calls `generate_ai_reply()` with entrypoint `web_chat`.
6. Public Web Chat is now stateless (`user_id=None`) because it has no authenticated identity.
7. Shared Guard, Tutor, Skill, prompt, provider, fallback, and telemetry flow runs.
8. JSON `{"reply": ...}` is returned.

### Agent API: `POST /api/agent/ask`

1. Payload size is checked.
2. `AI_TUTOR_API_KEY`/`X-API-Key` authentication fails closed.
3. Process-local IP rate limiting runs.
4. Legacy or capability payload is normalized.
5. Only `answer_question` and questions of at most 3,000 characters are accepted.
6. `dispatch_agent_capability()` calls the shared Tutor core with entrypoint `api`.
7. The existing response schema and `call_id` metadata are returned.

### Tutor API: `POST /api/tutor/ask`

1. Payload-size check.
2. API-key authentication.
3. Process-local IP rate limit.
4. JSON/question normalization and 3,000-character limit.
5. Process-local API-key daily quota check.
6. Shared Tutor core with entrypoint `api`.
7. Quota increment only after success.
8. Structured audit log and existing JSON schema.

### Messenger: `POST /webhook/messenger`

1. Feature gate checks `MESSENGER_ENABLED`.
2. Raw body is verified against `X-Hub-Signature-256` using `MESSENGER_APP_SECRET`.
3. Non-page, non-text, echo, attachment, read, and delivery events are ignored.
4. `message.mid` is deduplicated for 600 seconds.
5. A processing message is sent.
6. Background execution namespaces identity as `messenger:<sender_id>`.
7. Shared Tutor core runs with entrypoint `messenger`.
8. One final answer or fallback is sent.

### Core consistency

LINE, general Web Chat, Messenger, `/api/agent/ask`, `/api/tutor/ask`, and authenticated `/test` converge on `generate_tutor_answer()`. Channel validation, authentication, throttling, response formatting, and async behavior remain intentionally channel-specific. Rich Menu, FA, and course grading endpoints are deterministic/direct flows and do not use the general Tutor core.

## 4. Skill Loading Lifecycle

1. `skills/registry.py` constructs `SKILL_MANIFESTS` in Python.
2. `SkillCatalog` exposes enabled metadata sorted by priority.
3. `SkillRuntime.normalize_request()` creates `SkillRequest`.
4. `SkillRuntime.route()` chooses the first metadata domain/keyword match and returns `metadata_match` or `default`.
5. `SkillRuntime.get_skill()` lazily imports the manifest entrypoint.
6. `ModuleSkillAdapter` configures the model callback and invokes module-level `answer()`.
7. Loaded adapters remain cached for the process lifetime.
8. Import/invocation failure is caught by `TutorAgent`, which uses the general teaching path.

The contract is stable only for registry-backed chat skills. Adding one requires a module plus a new Python `SkillManifest`; folder metadata is not discovered. The iPAS AI course also requires direct imports/routes/templates/assets, and the net-zero course is not in `SKILL_MANIFESTS`. Therefore, “drop a folder, validate metadata, auto-discover” is not implemented.

The iPAS AI Application Planner has a strict seven-chapter index schema and validates identity fields, order, status, source Markdown, titles, quizzes, and answers. Its processor validates before an atomic temp-file replace. The net-zero planner assumes eight chapters by filename pattern, builds its runtime view from Markdown rather than its generated index, and its index script uses direct `Path.write_text()`.

Missing or malformed iPAS materials fail the affected course page/API with a controlled 503/500; they do not prevent Flask startup. Registry skill import failure falls back to general Tutor behavior. Skill content is cached after first load; deploy/restart is required to see on-disk updates.

## 5. Provider and Fallback Flow

Entrypoint policy selects OpenAI, Gemini, or DeepSeek. Each client receives both system and user prompts. Gemini and DeepSeek HTTP calls use a 60-second timeout; the OpenAI SDK uses its client defaults. LINE/Messenger add a 45-second outer wait, but the underlying future is not cancelled.

```text
selected provider
  -> complete_model_call()
  -> success: usage + provider/model/latency telemetry
  -> failure: error telemetry
     -> auth/4xx other than 429: re-raise, no fallback
     -> 429, 5xx, network error, timeout from Gemini/DeepSeek
        -> OpenAI exactly once
        -> fallback telemetry
        -> safe busy response if OpenAI is unavailable/fails
```

There is no recursion because OpenAI failures are never passed back into fallback. Empty/structurally invalid provider responses do not trigger fallback; this remains deferred.

## 6. Findings by Severity

### `AIT-P0-001`

**Severity:** P0  
**Title:** Public Web Chat shared every visitor's conversation context.  
**Evidence:** Before the fix, `main.web_chat()` defaulted or accepted `user_id="web-demo"` and `templates/index.html` always posted it; `memory/conversation_context.py:add_message()` stores complete turns by that key.  
**Impact:** One visitor's prior questions/answers could enter another visitor's prompt.  
**Trigger:** Two unrelated public clients used Web Chat before restart.  
**Recommendation:** Do not create persistent context without authenticated server-side identity.  
**Change Risk:** Low.  
**Status:** Fixed; public Web Chat now ignores caller identity and passes `None`.

### `AIT-P0-002`

**Severity:** P0  
**Title:** Agent API permitted anonymous, unbounded model calls.  
**Evidence:** `main.agent_ask()` previously parsed and dispatched before any call to `authenticate_tutor_api_request()`, payload-size guard, question-length guard, or rate limiter.  
**Impact:** External callers could consume provider quota and worker capacity without authorization.  
**Trigger:** Any POST to `/api/agent/ask`.  
**Recommendation:** Reuse the existing Tutor API controls before dispatch.  
**Change Risk:** Medium because callers must now provide the documented key.  
**Status:** Fixed.

### `AIT-P0-003`

**Severity:** P0  
**Title:** Public test endpoint bypassed API abuse controls.  
**Evidence:** `main.test_mode()` called `generate_ai_reply()` directly from a GET query.  
**Impact:** It was an alternate anonymous model-call path after protecting the formal APIs.  
**Trigger:** Any `GET /test?question=...`.  
**Recommendation:** Apply the same API key, length, and rate controls.  
**Change Risk:** Low.  
**Status:** Fixed.

### `AIT-P0-004`

**Severity:** P0  
**Title:** Messenger webhook POSTs were not authenticated.  
**Evidence:** `main.messenger_callback()` previously parsed JSON and called `handle_messenger_event()` without validating `X-Hub-Signature-256`; GET verification token is not POST authentication.  
**Impact:** Forged requests could trigger processing messages, LLM calls, and outbound Messenger messages.  
**Trigger:** Messenger enabled and an attacker posts a page-like payload.  
**Recommendation:** Verify the raw body with the Meta app secret before JSON dispatch.  
**Change Risk:** Medium; deployment must set `MESSENGER_APP_SECRET`.  
**Status:** Fixed.

### `AIT-P0-005`

**Severity:** P0  
**Title:** Messenger retries could enqueue duplicate LLM work and duplicate Push.  
**Evidence:** `messenger_webhook.handle_messenger_event()` previously submitted every text event and did not record `message.mid`; LINE already had a dedup guard.  
**Impact:** Retry delivery could duplicate provider charges and user-visible replies.  
**Trigger:** Meta retries the same message event.  
**Recommendation:** Process-local TTL deduplication by `message.mid` for the current single-worker deployment.  
**Change Risk:** Low.  
**Status:** Fixed.

### `AIT-P1-001`

**Severity:** P1  
**Title:** DeepSeek had no fallback and Gemini fallback classified only 429.  
**Evidence:** Before the fix, `main.ask_gpt()` called `fallback_from_gemini_rate_limit()` only for Gemini HTTP 429. DeepSeek 429/5xx/network errors and Gemini 5xx/network errors escaped.  
**Impact:** Provider-transient failures produced avoidable user errors; behavior differed by selected provider.  
**Trigger:** Retryable Gemini/DeepSeek failure.  
**Recommendation:** Classify only 429, 5xx, network, and timeout as retryable; fall back once to OpenAI; never fall back on authentication errors.  
**Change Risk:** Low.  
**Status:** Fixed in `is_retryable_provider_error()` and `fallback_to_openai()`.

### `AIT-P1-002`

**Severity:** P1  
**Title:** Public Web Chat had no input-length or rate boundary.  
**Evidence:** Before the fix, only the explicit FA branch called the IP limiter; the general branch accepted arbitrary message length and called `generate_ai_reply()`.  
**Impact:** A public caller could consume model and worker capacity at a high rate.  
**Trigger:** Repeated or very large `/web-chat` messages.  
**Recommendation:** Reuse the existing low-cost process-local limiter and 3,000-character boundary.  
**Change Risk:** Low.  
**Status:** Fixed.

### `AIT-P1-003`

**Severity:** P1  
**Title:** Runtime telemetry cannot reconstruct a request lifecycle.  
**Evidence:** `runtime_telemetry.TELEMETRY_FIELDS` has provider-call fields only. There is no request ID, guard result, route reason, selected Skill, lifecycle result, or phase timing. Guard early returns generate no telemetry. API `call_id` and FA `request_id` are log-only and are not propagated into provider records.  
**Impact:** Operators cannot answer why a route was selected, whether Guard rejected it, or correlate API/channel logs with provider attempts.  
**Trigger:** Any routing, early-return, or multi-provider incident.  
**Recommendation:** In a separate change, define one request correlation context and a backward-compatible lifecycle record without double-counting provider attempts.  
**Change Risk:** Medium.  
**Status:** Deferred to avoid changing dashboard semantics during security fixes.

### `AIT-P1-004`

**Severity:** P1  
**Title:** Adding a Skill still requires core Python wiring.  
**Evidence:** `skills/registry.py:SKILL_MANIFESTS` is a hard-coded tuple; `SkillRuntime.get_skill()` imports only registered entrypoints. iPAS Net-Zero and FA are direct `main.py` imports/routes rather than generic registered Tutor skills.  
**Impact:** A third/fourth/fifth Skill can be invisible to Tutor routing or require edits across registry, composition root, routes, UI, and tests.  
**Trigger:** Adding a new course folder without editing core code.  
**Recommendation:** First standardize one validated manifest contract across existing Skills; do not build a plugin framework.  
**Change Risk:** High.  
**Status:** Deferred.

### `AIT-P1-005`

**Severity:** P1  
**Title:** Little Tree is documented as retired but remains executable through retained active state.  
**Evidence:** `main.py` imports and constructs `LittleTreeAgent`; `_generate_tutor_answer()` calls it when `get_active_skill(user_id)` matches. `skills/registry.py` disables new routing, but tests explicitly preserve the legacy active-state path.  
**Impact:** Product behavior and architecture documentation disagree; residual state can bypass the normal Guard/Tutor path.  
**Trigger:** A process contains a legacy `little_tree_companion` active-skill key.  
**Recommendation:** Decide whether migration compatibility is still required, then remove the main-runtime branch and legacy state together in a dedicated change.  
**Change Risk:** Medium.  
**Status:** Deferred because removal changes preserved behavior.

### `AIT-P1-006`

**Severity:** P1  
**Title:** Rate limiting trusts `X-Forwarded-For` without a trusted-proxy boundary.  
**Evidence:** `main.tutor_api_client_ip()` always accepts the first caller-supplied `X-Forwarded-For` value.  
**Impact:** A direct caller can rotate the header and evade process-local IP limits.  
**Trigger:** Service is reachable without a proxy that overwrites the header.  
**Recommendation:** Use the deployment's verified proxy behavior or ignore forwarded headers unless explicitly configured.  
**Change Risk:** Medium because Render/proxy behavior must be confirmed.  
**Status:** Deferred; no deployment assumption was made.

### `AIT-P2-001`

**Severity:** P2  
**Title:** Duplicate Skill router can drift from production.  
**Evidence:** `agents/router.py:route()` is imported only by tests; production uses `SkillRuntime.route()`.  
**Impact:** Tests can pass against logic the application never executes.  
**Trigger:** One router changes without the other.  
**Recommendation:** Move tests to the production runtime, then delete the duplicate in a small cleanup.  
**Change Risk:** Low.  
**Status:** Deferred.

### `AIT-P2-002`

**Severity:** P2  
**Title:** Course schemas and index-write safety are inconsistent.  
**Evidence:** AI Application Planner enforces seven chapters and atomically writes a validated index; Net-Zero hard-codes eight filename-matched chapters and its processor writes JSON directly with `Path.write_text()`.  
**Impact:** Shared tooling cannot validate both Skills uniformly; a Net-Zero index write can be torn, and its runtime does not use the generated index as authority.  
**Trigger:** Interrupted Net-Zero processing or future shared tooling.  
**Recommendation:** Reuse the existing atomic JSON writer and document each Skill's course-specific chapter-count constraint before attempting schema convergence.  
**Change Risk:** Low for atomic write, high for schema convergence.  
**Status:** Deferred; it does not block the runtime fixes.

### `AIT-P2-003`

**Severity:** P2  
**Title:** Conversation and active-skill maps have no TTL or key-count bound.  
**Evidence:** `memory/conversation_context.py` caps each user at six turns but never expires user keys.  
**Impact:** A long-lived process accumulates inactive user IDs and retained short histories.  
**Trigger:** Many unique identified LINE/Messenger/API users over one process lifetime.  
**Recommendation:** Add a simple inactivity TTL only when production cardinality warrants it.  
**Change Risk:** Low.  
**Status:** Deferred; acceptable for current single-instance, low-volume deployment.

### `AIT-P2-004`

**Severity:** P2  
**Title:** Provider timeout behavior is not uniform and timed-out futures continue running.  
**Evidence:** Gemini/DeepSeek pass 60 seconds to `urlopen`; OpenAI uses SDK defaults. LINE/Messenger wait 45 seconds on a future but do not cancel underlying provider work. Web/API have no outer Tutor timeout.  
**Impact:** User timeout and provider resource lifetime differ; background worker capacity can remain occupied.  
**Trigger:** Slow or hung provider call.  
**Recommendation:** Establish one provider-call timeout contract in a dedicated reliability change.  
**Change Risk:** Medium.  
**Status:** Deferred.

### `AIT-P3-001`

**Severity:** P3  
**Title:** Dashboard documentation overstates route protection.  
**Evidence:** `/dashboard` serves only the HTML shell without authentication; `/observability` and `/api/runtime/telemetry` require the dashboard key. The shell fetches no data without the key. Some docs say all three routes are protected.  
**Impact:** Documentation is inaccurate, but telemetry data remains protected.  
**Trigger:** Opening `/dashboard` without a key.  
**Recommendation:** Document the shell/data distinction or consolidate routes later.  
**Change Risk:** Low.  
**Status:** Deferred.

## 7. Selected Fixes

| Finding | Files | Minimal change |
|---|---|---|
| AIT-P0-001 | `main.py`, `templates/index.html`, tests | Removed public client identity from Web Chat and disabled unauthenticated context |
| AIT-P0-002 | `main.py`, `.env.example`, tests | Reused existing API key, size, rate, and length controls |
| AIT-P0-003 | `main.py`, tests | Applied the same controls to `/test` |
| AIT-P0-004 | `messenger_webhook.py`, `main.py`, `.env.example`, tests | Added raw-body HMAC-SHA256 verification |
| AIT-P0-005 | `messenger_webhook.py`, tests | Added thread-safe 600-second `message.mid` deduplication |
| AIT-P1-001 | `main.py`, tests | Added retryable-error classification and one-way OpenAI fallback |
| AIT-P1-002 | `main.py`, tests | Applied existing process-local limiter and length boundary to all Web Chat |

## 8. Deferred Issues

The following were intentionally not changed:

- Request-ID/lifecycle telemetry: resolved by schema v2 in `docs/REQUEST_CORRELATION_TELEMETRY_CONTRACT.md`; distributed collection remains deferred.
- Automatic Skill discovery: existing Skills do not share a folder manifest contract.
- Little Tree deletion: legacy active-state behavior is explicitly tested and must be retired as a product decision.
- Trusted proxy handling: requires confirmation of deployment header rewriting.
- Router deletion: tests must first move to the production import path.
- iPAS schema convergence and Net-Zero index authority: this is a separate content-tooling contract change.
- Context TTL: acceptable limitation at current scale.
- Cross-process telemetry/file locks and distributed quota/deduplication: current Docker deployment is one worker.
- Provider timeout unification: separate behavior/risk decision.

## 9. Files Changed

- `.env.example`
- `main.py`
- `messenger_webhook.py`
- `templates/index.html`
- `tests/test_agent.py`
- `docs/AI_TUTOR_ARCHITECTURE_AUDIT_AND_OPTIMIZATION.md`

No formal教材 Markdown, chapter Markdown, chapter index, UI styling, or deployment file was changed.

## 10. Tests Added or Updated

Added or strengthened coverage for:

- Agent API fail-closed authentication.
- Agent API question-length rejection.
- `/test` authentication.
- Web Chat ignoring untrusted `user_id`.
- Stateless Web Chat without identity.
- Web Chat question length and rate limiting.
- Messenger HMAC signature verification and rejection.
- Messenger duplicate `message.mid` suppression.
- DeepSeek 5xx fallback exactly once.
- DeepSeek authentication error not falling back.
- Existing Agent API contract under authenticated dispatch.

Existing tests cover Guard, routing, context bounds, iPAS schemas, chapter-index regression, provider usage/fallback, API errors, rate/quota logic, dashboard authorization, malformed telemetry, missing Skill material, LINE deduplication, and course web routes.

## 11. Verification Results

Commands attempted:

1. `.\venv\Scripts\python.exe -m unittest discover -s tests -v`  
   Result: environment failure. The checked-in/local venv launcher could not create the process even though `pyvenv.cfg` points at `C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe`.
2. `py -m unittest discover -s tests -v`  
   Result: environment failure: `No installed Python found!`
3. `C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe -m unittest discover -s tests -v`  
   Baseline result: 217 passed.
4. Focused post-fix security/provider/channel test command  
   Result: 28 passed.
5. Full post-fix command using the same absolute interpreter  
   Intermediate result: 225 passed before the final `/test` and Web Chat boundary tests were added.
6. Final full-suite rerun using the same absolute interpreter  
   Result: **229 passed in 2.209s; 0 failures; 0 errors**.

Expected error logs in negative-path tests (deliberate provider/skill/telemetry failures) did not fail the suite. One existing `ResourceWarning` reports an unclosed Flask test response file for a Net-Zero card; this is test-resource hygiene, not a production request failure.

## 12. Remaining Risks

- Telemetry now has correlated schema-v2 request lifecycle and provider-attempt events; cross-process collection remains a deployment risk.
- API and Web rate limits, daily quotas, LINE/Messenger deduplication, context, and Skill caches are process-local.
- `X-Forwarded-For` trust can weaken IP limiting in a direct-access deployment.
- Identified entrypoints do not apply a common namespace centrally; Messenger is explicitly namespaced, while LINE/API rely on their native IDs.
- A LINE/Messenger 45-second timeout does not terminate the underlying future.
- OpenAI timeout behavior is not explicitly aligned with Gemini/DeepSeek.
- Invalid/empty provider responses do not invoke fallback.
- Messenger request-body size has no explicit application cap.
- Generic LINE/Messenger question-length controls rely mainly on platform constraints.

## 13. Answers to the 15 Questions

1. **Platform or assembled courses?** It has a shared platform core, but Skill onboarding is still partly assembled by hand. Verdict: an extensible tutor shell with course-specific coupling, not yet folder-driven extensibility.
2. **What must change for Skills 3–5?** At minimum `skills/registry.py` plus a Python entrypoint and tests. A course UI may also require `main.py`, template, assets, direct imports, and route tests. Net-Zero and FA demonstrate that coupling.
3. **Guard, Skill Router, Prompt Policy overlap?** The Guard owns product-boundary allow/deny; SkillRuntime owns domain selection; prompts repeat some behavioral boundaries. Responsibilities are conceptually distinct but policy text is duplicated and routing keywords overlap.
4. **Do LINE, Web Chat, and APIs share one Tutor Runtime?** General questions do. Rich Menu, FA, and iPAS grading/course routes intentionally bypass it.
5. **Is Little Tree completely removed?** No. New activation/registry routing is disabled, but imports, construction, active-skill check, prompt/runtime modules, and tests remain. Legacy active state can still execute it.
6. **Is DeepSeek fallback reliable?** After this change, retryable 429/5xx/network/timeout failures fall back once to OpenAI; 401/other non-retryable errors do not. Empty invalid responses remain a gap.
7. **Do all failure paths produce telemetry?** In-scope Tutor requests now record validation, Guard, routing/Skill, provider, fallback, and terminal failures. Deterministic iPAS grading/course routes remain explicitly out of scope.
8. **Can telemetry rebuild a request by request ID?** Yes for schema-v2 Tutor events. Legacy schema-v1 provider rows remain readable but cannot be retrospectively correlated.
9. **Can an old script regress chapter-index schema?** AI Application Planner is now strongly protected by schema validation and atomic replacement tests. Net-Zero uses a separate, weaker direct-write index script and runtime does not treat that index as authoritative.
10. **Does one Skill load failure stop the service?** Normally only that Skill/course is unavailable or Tutor falls back. Skills are lazy-loaded; iPAS material errors are handled per route. Import-time construction still exists for direct course modules, but current constructors do not eagerly read all content.
11. **Can context cross Skill or user?** The fixed public Web Chat no longer shares context. Identified users are separated by key and protected by a lock. Context can follow the same user across Skill changes; there is no automatic history reset, so cross-Skill semantic contamination remains possible. A caller that deliberately reuses another entrypoint's raw ID can also collide outside Messenger's namespace.
12. **Is Dashboard fully authenticated?** Telemetry data API and `/observability` are key-protected. `/dashboard` exposes only the HTML shell; it cannot fetch data without a key. Therefore data is protected, but route/documentation behavior is not uniform.
13. **Three issues most likely to explode on next Skill?** Hard-coded `SKILL_MANIFESTS`; incompatible per-course schema/chapter assumptions; direct `main.py`/UI wiring outside `SkillRuntime`.
14. **What is acceptable at single-instance low traffic?** In-memory context, quota/rate state, event deduplication, adapter cache, and thread-only telemetry append locking are acceptable documented limits while Docker remains one worker and traffic is low.
15. **Three refactors not to do now?** Do not introduce a plugin/agent framework; do not add a database/Redis/queue for current process-local state; do not unify/rewrite all course schemas and chapter indexes in one migration.

## 14. Recommended Next Step

Run a single-instance staging soak and compare request-level totals, provider-attempt totals, and fallback totals against access logs before enabling schema-v2 dashboard data for routine operations.

## 15. Explicit Non-Goals

- No new Agent, Skill, provider, database, queue, vector store, RAG system, frontend framework, deployment platform, or large dependency.
- No formal learning-content or chapter Markdown edits.
- No chapter-index regeneration.
- No model-selection order change beyond correcting retryable fallback behavior.
- No public response-schema redesign.
- No commit and no push.

## 16. Stabilization Update: Request Correlation Telemetry

The previously deferred request-correlation finding is now resolved for Tutor traffic:

- Schema v2 assigns one request ID at the Tutor entry boundary and retains it through validation, Guard, route, Skill, provider attempts, fallback, and final result.
- Request-level and provider-attempt-level events have separate counting semantics, so fallback does not inflate user-request totals.
- The reader remains compatible with schema v1, missing fields, missing request IDs, and malformed JSONL lines.
- The writer uses an explicit privacy allowlist and does not persist raw user identity, questions, prompts, answers, credentials, signatures, exception text, or context history.
- The existing telemetry API and dashboard fields remain available; additive `provider_attempts` and `rejected` metrics clarify the new semantics.

The normative contract, error taxonomy, event fields, privacy rules, tests, and deferred work are documented in `docs/REQUEST_CORRELATION_TELEMETRY_CONTRACT.md`.
