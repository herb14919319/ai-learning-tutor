# Weekly Facebook publishing

Each scheduled run calls the canonical one-shot job (`run_publish_once`), from `POST /internal/jobs/facebook-publish` or `python -m automation.facebook_content_job --publish`. A run does exactly one of these:

1. **Publish an approved post.** If the approval store holds an `approved` post, the run re-checks its exact hash and deterministic validation, calls the Facebook publisher once, and records it as `published`. It generates nothing new in that run.
2. **Prepare a draft.** Otherwise it selects a topic from `config/content_topics.json`, gets one Hung-yi Lee Skill answer, formats and validates the post, and runs semantic and registered-source review. The post is stored as `draft`. After a review PASS it moves to `reviewed`, and the run stops with `approval_required`. REJECT and UNCERTAIN stay `draft` and stop before Facebook.

Nothing is published in the run that generated it, and nothing is published without an explicit human approval of that exact post. There is no automatic rewriting or retry loop. `--dry-run` is unchanged: it generates and reviews, never touches the store and never calls Facebook.

## Approval workflow (draft → reviewed → approved → published)

| Transition | Who | Rule |
| --- | --- | --- |
| → draft | scheduled run | Every post that passes deterministic validation is stored with its exact text and SHA-256. The content id is derived from the hash, so the same text maps to the same record. |
| draft → reviewed | scheduled run (or `mark-reviewed`) | Only if the automated content review passed. A human cannot override a REJECT or UNCERTAIN. |
| reviewed → approved | human (`approve`) | Must name the exact `post_sha256`. Approval cannot skip review. |
| approved → published | next scheduled run | Only if the stored text still matches the approved hash; records `published_at` and the Facebook post id. |

The hash is authoritative. A wrong hash is refused, and a record whose text no longer matches its hash can never be approved or published. Repeating an operation is idempotent: the same draft text returns the existing record, re-approving keeps the original approval, and published content is never re-opened or posted again.

Operator CLI, run in the web service's Render Shell so it uses the same store as the HTTP job:

```bash
python -m automation.content_approval list
python -m automation.content_approval show <content_id>
python -m automation.content_approval approve <content_id> --sha256 <post_sha256> --note "checked"
python -m automation.content_approval status <content_id>
```

`show` prints the post, its hash, review result and timestamps. Read the post, then approve with the printed hash. Publishing happens on the next scheduled run.

## Approval store and Render

The store is one JSON file at `CONTENT_APPROVAL_STORE_PATH`, written atomically under a lock file. Render's filesystem is ephemeral and a disk cannot be attached to a Render Cron Job or shared between services, so:

- Attach a **Persistent Disk** to the AI Tutor **web service** (paid instance type) and set `CONTENT_APPROVAL_STORE_PATH` to a file on it, for example `/var/data/content_approvals.json`.
- Schedule runs through the **HTTP trigger** below, not a Render Cron Job. A Cron Job container would see an empty store.
- A disk limits the service to one instance and Render stops the old instance before starting the new one, so each deploy has a short downtime.

`--publish` and the HTTP trigger refuse to run (configuration error) while `CONTENT_APPROVAL_STORE_PATH` is unset, so nothing can be published without a store.

## Configuration

Set these on the web service, using the same model/content configuration as the Tutor service:

| Variable | Purpose |
| --- | --- |
| `MESSENGER_PAGE_ACCESS_TOKEN` | Page access token with `pages_manage_posts` for the configured Page |
| `MESSENGER_PAGE_ID` | Target Page |
| `MESSENGER_API_VERSION` | Graph API version; keep the deployment's existing configured version |
| `MODEL_PROVIDER` | `openai`, `gemini`, or `deepseek` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `DEEPSEEK_API_KEY` | Credential for the selected provider only |
| `CONTENT_APPROVAL_STORE_PATH` | Approval store file on the web service's persistent disk |
| `AI_TUTOR_CRON_SECRET` | Bearer secret for the HTTP trigger |

The provider's optional `OPENAI_MODEL`, `GEMINI_MODEL`, or `DEEPSEEK_MODEL` and `DEEPSEEK_BASE_URL` may be copied from the Tutor service to keep model behavior consistent. Configure secrets in Render, never in the repository. `python -m automation.facebook_content_job --check-config` checks only whether the required variables are present; it makes no model, source, or Facebook request. This cannot prove that a Page token has permission: verify `pages_manage_posts` and Page access with Meta before the first live run.

## Exit codes and HTTP results

| CLI exit | HTTP | Meaning |
| --- | --- | --- |
| 0 | 200 `"state": "published", "published": true` | Approved post published |
| 0 | 200 `"state": "reviewed"` (or `"published"` for already-posted text), `"published": false`, `content_id` | Waiting for human approval: a normal outcome |
| 0 | — | Review-passing dry run, or successful config check |
| 1 | 200 `"state": "review_rejected"` / `"review_uncertain"`, `"published": false` | Review REJECT or UNCERTAIN; article blocked safely |
| 2 | 503 `configuration_error` | Required production configuration absent or invalid |
| 3 | 500 `validation_failed` | Topic, generation, or deterministic validation failed |
| 4 | 502 `publish_failed` | Facebook publication failed; the post stays `approved` and the next run retries |
| 5 | 500 `internal_error` | Approval store cannot be read or written |

A review block is an expected safety result for an unsafe article, though it keeps a nonzero CLI exit for visibility. Do not force a PASS.

## External cron trigger

`POST /internal/jobs/facebook-publish` runs the same one-shot job as the CLI. Set `AI_TUTOR_CRON_SECRET` to a strong shared value on the web service and the cron host. The request body is ignored. The endpoint returns 401 for invalid authorization and 409 for an overlapping job in the same web process; other results are listed above. It does not return article text or secret values. The run lock is process-local, which matches the single instance a persistent disk allows.

```bash
curl --fail-with-body -X POST \
  -H "Authorization: Bearer $AI_TUTOR_CRON_SECRET" \
  "https://<AI-TUTOR-RENDER-HOST>/internal/jobs/facebook-publish"
```

Use one schedule only. Do not also run a Render Cron Job.
