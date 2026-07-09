# QA Review Package

## Requirement Summary

Second-round QA package for the dashboard, observability, and runtime telemetry fixes requested after Gemini QA Review. The implementation keeps the existing Tutor answer flow, router guard behavior, and LLM fallback behavior unchanged.

## Modified Files

- `.env.example`
- `AGENT_CARD.md`
- `README.md`
- `main.py`
- `runtime_telemetry.py`
- `templates/runtime_observability.html`
- `tests/test_runtime_telemetry.py`

Generated QA files:

- `review.patch`
- `diff_stat.txt`
- `changed_files.txt`
- `REVIEW.md`

## Architecture Impact

- Observability routes are now protected by a minimal dashboard API key guard.
- `/dashboard`, `/observability`, and `/api/runtime/telemetry` require a configured `DASHBOARD_API_KEY` or `OBSERVABILITY_API_KEY` and a matching `X-Dashboard-Key` request header.
- Existing public routes such as LINE webhook, `/web-chat`, `/healthz`, and the public web chat page are not tied to this dashboard key.
- Dashboard rendering was moved from a large inline route string in `main.py` to `templates/runtime_observability.html`.
- Runtime telemetry remains a lightweight local append-only JSONL observability log.
- Runtime telemetry is documented as operational telemetry, not conversational memory.

## Gemini BLOCK Items Fixed

- Protected dashboard and observability routes from anonymous access.
- Protected `/api/runtime/telemetry` from anonymous access.
- Added process-local `threading.Lock` around telemetry JSONL writes.
- Ensured each telemetry write serializes one complete JSONL line before appending.
- Kept telemetry write failures fail-open so model calls, webhook handling, and web chat are not crashed by telemetry I/O failures.
- Reduced `main.py` dashboard responsibility by moving the HTML/JS/CSS into a template.
- Added tests for missing key, wrong key, correct key, and telemetry write fail-open behavior.

## Known Risks

- The telemetry write lock is process-local only. It does not coordinate writes across multiple worker processes or multiple deployed instances.
- Telemetry remains synchronous lightweight local append-only I/O. It is fail-open but still runs in the request path.
- The dashboard key is a minimal shared-secret mechanism, not a full user/session authentication system.

## Test Results

- `python -m py_compile main.py runtime_telemetry.py tests\test_runtime_telemetry.py`: passed
- `python -m unittest tests.test_runtime_telemetry`: 13 tests passed
- `python -m unittest discover -s tests`: 142 tests passed
- `git diff --check`: passed

Notes:

- Tests were run with the bundled Codex Python runtime because the project `venv` launcher points to a missing base Python executable in this workspace.
- The telemetry fail-open tests intentionally log `Runtime telemetry write failed` while still passing.
