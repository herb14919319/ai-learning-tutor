"""R5: persistent draft → reviewed → approved → published workflow for Facebook posts."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main
import tests
from automation import content_approval, facebook_content_job
from automation.approval_store import ApprovalStore, ApprovalStoreError, ApprovalTransitionError, post_sha256
from automation.content_review import ContentReviewDecision, ContentReviewResult
from automation.facebook_content_job import (
    EXIT_CODES,
    JobStatus,
    is_publish_approved,
    run_governed_publish,
    run_job,
    store_approval_lookup,
)
from automation.facebook_publisher import PublishResult

PASS = ContentReviewResult(ContentReviewDecision.PASS, (), "No material issue found.")
REJECT = ContentReviewResult(ContentReviewDecision.REJECT, (), "Material error.")


class GovernanceTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.topics = root / "topics.json"
        self.topics.write_text(json.dumps(["Tool、Skill、MCP 差在哪？"], ensure_ascii=False), encoding="utf-8")
        self.store_path = root / "disk" / "approvals.json"
        self.store = ApprovalStore(self.store_path)
        self.publisher = Mock(return_value=PublishResult(True, post_id="page_post_1"))
        self.answer = "Tool 是能力，Skill 是流程，MCP 是協定。"

    def defaults(self, reviewer=PASS, publisher=None):
        return {
            "topics_path": self.topics,
            "topic_selector": lambda topics: topics[0],
            "skill_answerer": lambda topic: self.answer,
            "reviewer": lambda topic, post: reviewer,
            "publisher": publisher or self.publisher,
        }

    def run_once(self, **kwargs):
        return run_governed_publish(self.store, **self.defaults(**kwargs))

    def approve_only_record(self):
        (record,) = self.store.list_records()
        return self.store.approve(record.content_id, record.post_sha256, note="checked by owner")


class WorkflowTest(GovernanceTestCase):
    def test_passing_draft_is_stored_as_reviewed_and_not_published(self):
        result = self.run_once()
        (record,) = self.store.list_records()
        self.assertEqual((result.status, result.approval_state, result.content_id), (JobStatus.APPROVAL_REQUIRED, "reviewed", record.content_id))
        self.assertEqual((record.state, record.review_decision, record.post_sha256), ("reviewed", "pass", post_sha256(result.post)))
        self.assertIsNotNone(record.reviewed_at)
        self.assertIsNone(record.approved_at)
        self.publisher.assert_not_called()

    def test_rejected_draft_stays_draft_and_cannot_be_marked_reviewed(self):
        result = self.run_once(reviewer=REJECT)
        (record,) = self.store.list_records()
        self.assertEqual((result.status, record.state, record.review_decision), (JobStatus.REVIEW_REJECTED, "draft", "reject"))
        with self.assertRaises(ApprovalTransitionError):
            self.store.mark_reviewed(record.content_id)
        with self.assertRaises(ApprovalTransitionError):
            self.store.approve(record.content_id, record.post_sha256)  # approval cannot skip review

    def test_reviewed_content_cannot_publish(self):
        self.run_once()
        result = self.run_once()  # same deterministic post: still waiting for approval
        self.assertEqual((result.status, result.approval_state), (JobStatus.APPROVAL_REQUIRED, "reviewed"))
        self.assertEqual(len(self.store.list_records()), 1)
        self.publisher.assert_not_called()
        blocked = run_job(publish=True, approval_lookup=store_approval_lookup(self.store), **self.defaults())
        self.assertEqual(blocked.status, JobStatus.APPROVAL_REQUIRED)
        self.publisher.assert_not_called()

    def test_exact_approved_hash_publishes_once_and_records_publication(self):
        self.run_once()
        approved = self.approve_only_record()
        result = self.run_once()
        self.publisher.assert_called_once_with(approved.post)
        record = self.store.get(approved.content_id)
        self.assertEqual((result.status, result.post_id, result.approval_state), (JobStatus.PUBLISHED, "page_post_1", "published"))
        self.assertEqual((record.state, record.post_id, record.note), ("published", "page_post_1", "checked by owner"))
        self.assertIsNotNone(record.published_at)
        self.assertLessEqual(record.reviewed_at, record.approved_at)
        self.assertLessEqual(record.approved_at, record.published_at)

    def test_repeated_runs_never_duplicate_a_published_post(self):
        self.run_once()
        self.approve_only_record()
        self.run_once()
        again = self.run_once()  # regenerates the identical post
        self.assertEqual((again.status, again.approval_state), (JobStatus.APPROVAL_REQUIRED, "published"))
        self.publisher.assert_called_once()
        (record,) = self.store.list_records()
        self.assertEqual(self.store.mark_published(record.content_id, "other"), record)  # idempotent
        self.assertFalse(is_publish_approved(record.post, store_approval_lookup(self.store)(record.post)))

    def test_new_drafts_wait_while_older_approved_post_is_published_first(self):
        self.run_once()
        first = self.approve_only_record()
        self.answer = "第二篇草稿。"
        result = self.run_once()  # publishes the approved post instead of generating
        self.assertEqual(result.content_id, first.content_id)
        self.assertEqual(len(self.store.list_records()), 1)


class HashAuthorityTest(GovernanceTestCase):
    def test_wrong_or_stale_hash_is_refused(self):
        self.run_once()
        (record,) = self.store.list_records()
        with self.assertRaisesRegex(ApprovalTransitionError, "does not match"):
            self.store.approve(record.content_id, post_sha256(record.post + " edited"))
        self.assertEqual(self.store.get(record.content_id).state, "reviewed")

    def test_content_changed_after_approval_never_publishes(self):
        self.run_once()
        approved = self.approve_only_record()
        payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        payload["records"][approved.content_id]["post"] += "（偷改）"
        self.store_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        result = self.run_once()
        self.assertEqual(result.status, JobStatus.APPROVAL_REQUIRED)
        self.assertIn("no longer matches", result.errors[0])
        self.publisher.assert_not_called()
        self.assertFalse(self.store.get(approved.content_id).content_intact)
        with self.assertRaises(ApprovalTransitionError):
            self.store.approve(approved.content_id, approved.post_sha256)


class IdempotencyAndTransitionsTest(GovernanceTestCase):
    def test_repeated_operations_are_idempotent(self):
        self.run_once()
        (record,) = self.store.list_records()
        self.assertEqual(self.store.record_draft(record.topic, record.post, "pass"), record)
        self.assertEqual(self.store.mark_reviewed(record.content_id), record)
        first = self.store.approve(record.content_id, record.post_sha256)
        second = self.store.approve(record.content_id, record.post_sha256.upper(), note="again")
        self.assertEqual(first, second)
        published = self.store.mark_published(record.content_id, "p1")
        self.assertEqual(self.store.approve(record.content_id, record.post_sha256), published)
        self.assertEqual(self.store.mark_reviewed(record.content_id), published)

    def test_illegal_transitions_are_refused(self):
        draft = self.store.record_draft("t", "draft body", "pass")
        with self.assertRaises(ApprovalTransitionError):
            self.store.mark_published(draft.content_id, "p")
        with self.assertRaises(ApprovalTransitionError):
            self.store.approve(draft.content_id, draft.post_sha256)
        self.store.mark_reviewed(draft.content_id)
        with self.assertRaises(ApprovalTransitionError):
            self.store.mark_published(draft.content_id, "p")
        with self.assertRaises(ApprovalTransitionError):
            self.store.approve("fb-unknown", "0" * 64)

    def test_only_approved_records_are_queued_for_publishing(self):
        draft = self.store.record_draft("t", "draft body", "pass")
        reviewed = self.store.mark_reviewed(self.store.record_draft("t", "reviewed body", "pass").content_id)
        self.assertIsNone(self.store.next_approved())
        approved = self.store.approve(reviewed.content_id, reviewed.post_sha256)
        self.assertEqual(self.store.next_approved(), approved)
        self.store.mark_published(approved.content_id, "p")
        self.assertIsNone(self.store.next_approved())
        self.assertEqual(self.store.get(draft.content_id).state, "draft")

    def test_store_writes_atomically_and_releases_its_lock(self):
        self.run_once()
        self.assertEqual(sorted(p.name for p in self.store_path.parent.iterdir()), ["approvals.json"])
        self.assertEqual(json.loads(self.store_path.read_text(encoding="utf-8"))["schema_version"], 1)


class FailureTest(GovernanceTestCase):
    def test_publish_failure_fails_and_keeps_approval_for_retry(self):
        self.run_once()
        approved = self.approve_only_record()
        failing = Mock(return_value=PublishResult(False, error="Facebook Graph API error: 500"))
        result = self.run_once(publisher=failing)
        self.assertEqual((result.status, EXIT_CODES[result.status]), (JobStatus.PUBLISH_FAILED, 4))
        self.assertEqual(self.store.get(approved.content_id).state, "approved")
        self.assertEqual(self.run_once().status, JobStatus.PUBLISHED)

    def test_corrupt_store_is_an_infrastructure_failure(self):
        self.store_path.parent.mkdir(parents=True)
        self.store_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ApprovalStoreError):
            self.run_once()
        self.publisher.assert_not_called()

    def test_generation_failure_still_fails(self):
        result = run_governed_publish(self.store, **{**self.defaults(), "skill_answerer": Mock(side_effect=RuntimeError("provider down"))})
        self.assertEqual((result.status, EXIT_CODES[result.status]), (JobStatus.VALIDATION_FAILED, 3))
        self.assertEqual(self.store.list_records(), [])


class CliAndHttpTest(GovernanceTestCase):
    def setUp(self):
        super().setUp()
        for patcher in (
            patch.dict(os.environ, {"CONTENT_APPROVAL_STORE_PATH": str(self.store_path), "AI_TUTOR_CRON_SECRET": "cron-secret"}),
            patch.object(facebook_content_job, "production_config_errors", return_value=()),
            patch.object(facebook_content_job, "load_dotenv"),
            patch.object(content_approval, "load_dotenv"),
            patch.dict(run_governed_publish.__kwdefaults__, self.defaults()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def job_cli(self, *args):
        with patch("sys.argv", ["job", *args]), contextlib.redirect_stdout(io.StringIO()) as out:
            code = facebook_content_job.main()
        return code, out.getvalue()

    def approval_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = content_approval.main(list(args))
        return code, out.getvalue()

    def http(self):
        return main.app.test_client().post("/internal/jobs/facebook-publish", headers={"Authorization": "Bearer cron-secret"})

    def test_cli_approval_required_run_exits_successfully(self):
        code, output = self.job_cli("--publish")
        self.assertEqual(code, 0)
        self.assertIn("status: approval_required", output)
        self.assertIn("approval_state: reviewed", output)
        self.assertIn("publish_allowed: NO", output)
        self.publisher.assert_not_called()

    def test_http_and_both_clis_share_one_store(self):
        first = self.http()
        content_id = first.json["content_id"]
        self.assertEqual((first.status_code, first.json), (200, {"ok": True, "state": "reviewed", "published": False, "content_id": content_id}))

        code, listing = self.approval_cli("list")
        self.assertEqual(code, 0)
        self.assertIn(f"{content_id}\treviewed", listing)
        code, shown = self.approval_cli("show", content_id)
        sha = next(line.split(": ", 1)[1] for line in shown.splitlines() if line.startswith("post_sha256: "))
        self.assertIn(self.answer, shown)
        self.assertEqual(self.approval_cli("approve", content_id, "--sha256", "0" * 64)[0], 1)  # wrong hash refused
        self.assertEqual(self.approval_cli("approve", content_id, "--sha256", sha, "--note", "ok"), (0, f"{content_id}: approved\n"))
        self.assertEqual(self.approval_cli("approve", content_id, "--sha256", sha)[0], 0)  # idempotent

        code, output = self.job_cli("--publish")
        self.assertEqual(code, 0)
        self.assertIn("status: published", output)
        self.assertEqual(self.approval_cli("status", content_id), (0, "published\n"))
        again = self.http()
        self.assertEqual((again.json["state"], again.json["published"]), ("published", False))
        self.publisher.assert_called_once()

    def test_infrastructure_failures_still_fail(self):
        self.store_path.parent.mkdir(parents=True)
        self.store_path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.job_cli("--publish")[0], 5)
        self.assertEqual(self.approval_cli("list")[0], 5)
        response = self.http()
        self.assertEqual((response.status_code, response.json), (500, {"ok": False, "state": "internal_error"}))

        self.store_path.unlink()
        with patch.dict(os.environ, {"CONTENT_APPROVAL_STORE_PATH": ""}):
            self.assertEqual(self.approval_cli("list")[0], 2)
            self.assertEqual(self.job_cli("--publish")[0], 2)
            self.assertEqual(self.http().status_code, 503)
        self.publisher.assert_not_called()

    def test_dry_run_never_touches_the_store_or_facebook(self):
        with patch.dict(run_job.__kwdefaults__, self.defaults()):
            code, output = self.job_cli("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("status: generated", output)
        self.assertFalse(self.store_path.exists())
        self.publisher.assert_not_called()


class NoNetworkTest(GovernanceTestCase):
    def test_workflow_makes_no_external_network_attempts(self):
        before = list(tests.BLOCKED_NETWORK_ATTEMPTS)
        self.run_once()
        self.approve_only_record()
        self.run_once()
        self.assertEqual(tests.BLOCKED_NETWORK_ATTEMPTS, before)


if __name__ == "__main__":
    unittest.main()
