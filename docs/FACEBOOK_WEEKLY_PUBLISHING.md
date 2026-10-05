# Weekly Facebook publishing

The one-shot job is `python -m automation.facebook_content_job --publish`. It selects a topic from `config/content_topics.json`, gets one Hung-yi Lee Skill answer, formats and validates the post, runs semantic and registered-source review, and calls the Facebook publisher at most once only after a final PASS **and** an explicit human approval of that exact post. REJECT and UNCERTAIN stop before Facebook. There is no automatic rewriting or retry loop.

## Human approval gate (fail closed)

An automated PASS is not permission to publish. Before the publisher is called, `run_job` looks up an approval record for the post. It publishes only when the record's state is `approved` and its `post_sha256` matches the SHA-256 of the exact post body. Draft or reviewed records, a missing record, a mismatched hash, or a failing lookup all stop with `approval_required` (exit 1, HTTP 200 `"published": false`).

No approval store exists yet. The production default (`no_approval_store`) always returns no record, so `--publish`, the Render Cron Job, and `POST /internal/jobs/facebook-publish` currently generate and review a draft but **never publish**. The target lifecycle is draft → reviewed → approved → published; a persistent approval workflow is planned separately. `--dry-run` is unchanged: it never consults approval and never calls Facebook.

## Configuration

Set these on the Render Cron Job, using the same model/content configuration as the Tutor service:

| Variable | Purpose |
| --- | --- |
| `MESSENGER_PAGE_ACCESS_TOKEN` | Page access token with `pages_manage_posts` for the configured Page |
| `MESSENGER_PAGE_ID` | Target Page |
| `MESSENGER_API_VERSION` | Graph API version; keep the deployment's existing configured version |
| `MODEL_PROVIDER` | `openai`, `gemini`, or `deepseek` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `DEEPSEEK_API_KEY` | Credential for the selected provider only |

The provider's optional `OPENAI_MODEL`, `GEMINI_MODEL`, or `DEEPSEEK_MODEL` and `DEEPSEEK_BASE_URL` may be copied from the Tutor service to keep model behavior consistent. Share a Render Environment Group if one already supplies these values. Configure secrets in Render, never in the repository. `python -m automation.facebook_content_job --check-config` checks only whether the required variables are present; it makes no model, source, or Facebook request. This cannot prove that a Page token has permission: verify `pages_manage_posts` and Page access with Meta before the first live run.

## Render dashboard Cron Job

The repository has no Render Blueprint, so create a dashboard managed **Cron Job** using the current repository on branch `main`. Use the existing service's build method. For a native Python environment, the build command is `pip install -r requirements.txt`. For a Docker deployment, use the existing `Dockerfile` and override the service command with the job command below. Confirm the selected Render runtime supports the repository's bundled Hung-yi Lee skill dependencies.

| Setting | Value |
| --- | --- |
| Command | `python -m automation.facebook_content_job --publish` |
| Schedule | `0 4 * * 3` |
| Time | Wednesday 04:00 UTC = Wednesday 12:00 Asia/Taipei |

Run `python -m automation.facebook_content_job --check-config` in the Cron environment before enabling the first scheduled run. The job exits after one result. A connected `main` branch may trigger a deploy of existing services when pushed; check Render's auto-deploy setting before pushing if avoiding that deploy matters.

## Exit codes and operations

| Exit | Meaning |
| --- | --- |
| 0 | Published, review-passing dry-run, or successful config check |
| 1 | Review REJECT or UNCERTAIN, or human approval missing; article blocked safely |
| 2 | Required production configuration absent or invalid |
| 3 | Topic, generation, or deterministic validation failed |
| 4 | Facebook publication failed |

A review block is an expected safety result for an unsafe article, though Render records the nonzero exit for visibility. The current MCP topic remains in the topic pool. Run `python -m automation.facebook_content_job --dry-run` to inspect it without posting. Do not force a PASS.

The job reads repository configuration and does not need files saved by earlier Cron runs. It does not persist topic history, review history, or Facebook post IDs. A single execution calls the publisher at most once. Duplicate prevention across separate runs and retry attempts is not persistent; do not rerun a successful publication without checking the Page first.

## External Linux cron trigger

The existing Flask service also exposes `POST /internal/jobs/facebook-publish`. Set `AI_TUTOR_CRON_SECRET` to a strong shared value in the Render web service and in the Linux cron host's environment. The request body is ignored; the server selects the topic and invokes the same one-shot publish function used by the CLI. The endpoint returns HTTP 200 for publication or a safe review or approval block, 401 for invalid authorization, 409 for an overlapping job in the same web process, 503 for missing configuration, and 500/502 for runtime or publishing failures. It does not return article text or secret values. The lock is process-local; multiple Render processes or instances are not coordinated.

Example command for the eventual external cron entry (do not run until ready to permit a real post):

```bash
curl --fail-with-body -X POST \
  -H "Authorization: Bearer $AI_TUTOR_CRON_SECRET" \
  "https://<AI-TUTOR-RENDER-HOST>/internal/jobs/facebook-publish"
```

Use either this external trigger or a Render Cron Job for a given schedule to avoid duplicate runs.
