# Request Correlation Telemetry Contract

## 1. Purpose

This contract gives every Tutor request one operational identity from entrypoint to final result. It separates user-request outcomes from provider attempts so a fallback remains one request, while still exposing the cost and reliability of each provider call.

## 2. Scope

Schema v2 applies to Tutor traffic entering through LINE, Messenger, Web Chat, `/api/agent/ask`, `/api/tutor/ask`, and authenticated `/test`. Explicit FA Web Chat requests also use the contract because they already share the model-call boundary.

Health checks, assets, dashboard pages, Rich Menu operations, and deterministic iPAS grading/course routes are outside request tracing. Extending correlation to those deterministic routes is deferred until they share a common runtime boundary.

## 3. Request Lifecycle

The normal lifecycle is:

```text
request_received
request_validated
guard_evaluated
route_selected
skill_selected
provider_attempted
[provider_failed]
[provider_fallback]
request_completed | request_failed
```

Validation failures terminate with `request_failed`. Guard rejection terminates with `request_completed` and status `rejected`, because the runtime deliberately returned a policy response. Skill failure may route to `general`; the failed Skill event and fallback route remain visible while the request may still complete successfully.

## 4. Schema Versioning

New events have `schema_version: 2`. Existing provider-call rows without a version are schema v1. The JSONL file remains append-only; no migration or rewrite is required.

Readers must:

- recognize v1 rows without `schema_version`, `event`, or `request_id`;
- recognize v2 events by `schema_version == 2` and a string `event`;
- ignore unknown or nullable fields;
- skip malformed JSONL lines without failing the dashboard.

## 5. Event Types

| Event | Level | Meaning |
| --- | --- | --- |
| `request_received` | request | An in-scope entrypoint accepted the runtime invocation. |
| `request_validated` | request | Authentication, size, shape, rate, and quota checks succeeded or failed. |
| `guard_evaluated` | request | The learning-boundary Guard allowed, rejected, or was intentionally skipped. |
| `route_selected` | request | A stable runtime route was selected. A Skill failure may produce a second general route. |
| `skill_selected` | request | The selected stable Skill ID, including `general`. |
| `provider_attempted` | provider attempt | One terminal provider attempt with status, latency, model, and available token counts. |
| `provider_failed` | provider attempt detail | A failed attempt and its stable error category. It does not increment attempt count again. |
| `provider_fallback` | request | A retryable failure selected another provider. |
| `request_completed` | request | The runtime returned a successful or deliberately rejected result. |
| `request_failed` | request | The request ended because validation, routing, provider, or internal processing failed. |

## 6. Required Fields

Every v2 event contains:

| Field | Type | Allowed values / rule |
| --- | --- | --- |
| `schema_version` | integer | `2` |
| `timestamp` | string | UTC ISO-8601 |
| `request_id` | string | Opaque UUID-derived identifier, unchanged for the lifecycle |
| `event` | string | One event type from section 5 |
| `entrypoint` | string | `line`, `messenger`, `web_chat`, `api_agent`, `api_tutor`, or `test` |
| `user_scope` | string | `anonymous`, `authenticated`, or `channel_user` |
| `status` | string | Event-specific status such as `received`, `success`, `error`, `rejected`, `skipped`, or `selected` |

The writer emits a fixed allowlisted record shape. Fields that do not apply to an event are JSON `null`; booleans remain JSON booleans.

## 7. Optional Fields

Event-specific fields are:

- Routing: `route`, `route_reason`, `skill_id`.
- Guard: `guard_result`, `guard_reason`.
- Provider: `provider`, `provider_attempt`, `model`, `fallback`, `fallback_from`, `fallback_to`.
- Result: `error_category`, `latency_ms`.
- Safe volume metadata: `question_length`, `context_turn_count`.
- Usage: `input_tokens`, `output_tokens`, `total_tokens`.

`latency_ms` on `provider_attempted` is attempt latency. `latency_ms` on a terminal request event is end-to-end runtime latency. Missing provider usage remains `null`, not zero.

## 8. Error Taxonomy

Only stable categories are contract values:

- `validation_error`
- `authentication_error`
- `rate_limit_error`
- `guard_rejected`
- `routing_error`
- `skill_unavailable`
- `provider_rate_limit`
- `provider_timeout`
- `provider_network_error`
- `provider_server_error`
- `provider_auth_error`
- `provider_invalid_response`
- `internal_error`

Exception classes, exception messages, provider response bodies, and tracebacks are not telemetry fields.

## 9. Provider Attempt Semantics

`provider_attempt` starts at `1` within each request context and increments once before each provider call. A completed call writes one `provider_attempted` event. A failed call also writes `provider_failed` with the same attempt number.

A retryable DeepSeek or Gemini failure writes:

```text
provider_attempted(attempt=1, status=error)
provider_failed(attempt=1)
provider_fallback(from=original, to=openai)
provider_attempted(attempt=2, status=success)
```

All events retain the original `request_id`. Provider authentication failures are non-retryable and do not write `provider_fallback`.

## 10. Request Counting Semantics

For schema v2:

- user requests count only terminal `request_completed` and `request_failed` events;
- successes count terminal status `success`;
- errors count terminal status `error`;
- deliberate Guard rejections count separately as `rejected`;
- provider attempts count `provider_attempted`;
- fallbacks count `provider_fallback`;
- provider token and error aggregates come from provider-attempt events.

Therefore one DeepSeek failure followed by one successful OpenAI fallback is: one user request, two provider attempts, one fallback, one successful user request, one failed DeepSeek attempt, and one successful OpenAI attempt.

Schema v1 cannot reconstruct request identity. Each legacy row keeps its historical request-counting behavior, while also appearing as one provider attempt.

## 11. Privacy Rules

The telemetry writer is an allowlist. It may record IDs and categories defined in this contract, but must not record:

- raw or hashed user IDs;
- IP addresses or caller-provided identity;
- API keys, access tokens, or Messenger signatures;
- raw question, prompt, system prompt, answer, provider body, or context history;
- exception messages or tracebacks.

`user_scope` describes only the authentication class. `request_id` is random and must not encode user identity.

## 12. Backward Compatibility

The storage path and JSONL encoding remain unchanged. Existing telemetry API fields remain available: `total_requests`, `success`, `error`, `total_tokens`, `fallback_count`, `by_entrypoint`, `by_provider`, and `recent_requests`.

Schema v2 adds `provider_attempts` and `rejected`. `by_provider[*].requests` remains named that way for API compatibility, but represents provider attempts for v2 rows. The dashboard labels that column “Attempts.” Missing files return an empty summary, malformed/partial JSON lines are skipped, and missing request IDs never crash aggregation.

## 13. Failure Behavior

Telemetry is fail-open. Directory creation, append, serialization, or read failures are logged through the application logger and must not replace the Tutor response or trigger recursive telemetry.

Writes use UTF-8 append mode under a process-local lock. This protects concurrent threads in the current single-process deployment. Cross-process atomicity and distributed collection are deferred.

## 14. Tests

The contract is protected by tests for:

- unique request IDs and same-ID lifecycle propagation;
- Guard rejection reason and terminal status;
- selected route and Skill ID;
- retryable provider failure, fallback, and second attempt;
- non-retryable provider authentication failure;
- early API validation terminal events;
- v2 request/attempt/fallback aggregation;
- v1 compatibility and malformed-line tolerance;
- writer allowlist exclusion of sensitive values;
- the existing full regression suite.

## 15. Deferred Work

- Distributed/cross-process telemetry locking and collection.
- Context propagation into infrastructure work that runs outside the Tutor request boundary.
- Deterministic iPAS grading/course request tracing.
- A dedicated request-detail UI grouped by `request_id`.
- Context-turn count population after a stable cross-Skill context policy is defined.

## 16. Non-Goals

This contract does not add OpenTelemetry, Prometheus, Grafana, Sentry, Redis, a queue, an event bus, a database, or another dependency-injection/tracing framework. It does not rewrite the dashboard, Guard, Router, Skill Runtime, provider abstraction, public response schemas, content, or chapter indexes.
