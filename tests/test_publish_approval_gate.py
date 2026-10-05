import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main
from automation import facebook_content_job
from automation.content_review import ContentReviewDecision, ContentReviewResult
from automation.facebook_content_job import (
    EXIT_CODES,
    ApprovalRecord,
    ApprovalState,
    ContentJobResult,
    JobStatus,
    post_digest,
    run_job,
    run_publish_once,
)
from automation.facebook_publisher import PublishResult


PASS_REVIEW = ContentReviewResult(ContentReviewDecision.PASS, (), "No material issue found.")


class PublishApprovalGateTest(unittest.TestCase):
    """No explicit human approval of the exact post means no publish."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.topics_path = Path(self.temp_dir.name) / "topics.json"
        self.topics_path.write_text(json.dumps(["Topic A"]), encoding="utf-8")
        self.publisher = Mock(return_value=PublishResult(True, post_id="page_1"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_publish(self, **kwargs):
        return run_job(
            publish=True,
            topics_path=self.topics_path,
            skill_answerer=lambda topic: "generated article",
            reviewer=lambda topic, post: PASS_REVIEW,
            publisher=self.publisher,
            **kwargs,
        )

    def assert_blocked(self, result):
        self.assertEqual(result.status, JobStatus.APPROVAL_REQUIRED)
        self.assertFalse(result.publish_allowed)
        self.assertIsNone(result.post_id)
        self.publisher.assert_not_called()

    def test_reviewed_but_unapproved_content_cannot_publish(self):
        for state in (ApprovalState.DRAFT, ApprovalState.REVIEWED):
            with self.subTest(state=state):
                self.publisher.reset_mock()
                result = self.run_publish(
                    approval_lookup=lambda post, state=state: ApprovalRecord(state, post_digest(post))
                )
                self.assert_blocked(result)
                self.assertEqual(result.review.decision, ContentReviewDecision.PASS)

    def test_missing_approval_cannot_publish(self):
        self.assert_blocked(self.run_publish())
        self.assert_blocked(self.run_publish(approval_lookup=lambda post: None))

    def test_failed_or_malformed_approval_lookup_cannot_publish(self):
        def broken_lookup(post):
            raise RuntimeError("approval store unavailable")

        malformed = (
            {"state": "approved", "post_sha256": "x"},
            "approved",
            True,
            ApprovalRecord("approved", "not-a-hash"),
            ApprovalRecord(ApprovalState.APPROVED, "非十六進位"),
            ApprovalRecord(ApprovalState.APPROVED, None),
        )
        self.assert_blocked(self.run_publish(approval_lookup=broken_lookup))
        for record in malformed:
            with self.subTest(record=record):
                self.assert_blocked(self.run_publish(approval_lookup=lambda post, record=record: record))

    def test_approval_of_different_content_cannot_publish(self):
        result = self.run_publish(
            approval_lookup=lambda post: ApprovalRecord(ApprovalState.APPROVED, post_digest(post + " edited"))
        )
        self.assert_blocked(result)

    def test_explicitly_approved_content_reaches_existing_publish_path(self):
        lookup = Mock(side_effect=lambda post: ApprovalRecord(ApprovalState.APPROVED, post_digest(post)))
        result = self.run_publish(approval_lookup=lookup)

        self.assertEqual(result.status, JobStatus.PUBLISHED)
        self.assertEqual(result.post_id, "page_1")
        self.assertTrue(result.publish_allowed)
        lookup.assert_called_once_with(result.post)
        self.publisher.assert_called_once_with(result.post)

    def test_approval_does_not_bypass_automated_review(self):
        reject = ContentReviewResult(ContentReviewDecision.REJECT, (), "Material error.")
        result = run_job(
            publish=True,
            topics_path=self.topics_path,
            skill_answerer=lambda topic: "generated article",
            reviewer=lambda topic, post: reject,
            publisher=self.publisher,
            approval_lookup=lambda post: ApprovalRecord(ApprovalState.APPROVED, post_digest(post)),
        )
        self.assertEqual(result.status, JobStatus.REVIEW_REJECTED)
        self.publisher.assert_not_called()

    def test_dry_run_never_publishes_or_consults_approval(self):
        lookup = Mock(side_effect=lambda post: ApprovalRecord(ApprovalState.APPROVED, post_digest(post)))
        result = run_job(
            publish=False,
            topics_path=self.topics_path,
            skill_answerer=lambda topic: "generated article",
            reviewer=lambda topic, post: PASS_REVIEW,
            publisher=self.publisher,
            approval_lookup=lookup,
        )
        self.assertEqual(result.status, JobStatus.GENERATED)
        self.assertFalse(result.publish_allowed)
        lookup.assert_not_called()
        self.publisher.assert_not_called()

    def test_cli_dry_run_reports_missing_approval_and_never_publishes(self):
        with patch.object(facebook_content_job, "load_dotenv"), patch.dict(
            run_job.__kwdefaults__,
            {
                "topics_path": self.topics_path,
                "skill_answerer": lambda topic: "generated article",
                "reviewer": lambda topic, post: PASS_REVIEW,
                "publisher": self.publisher,
            },
        ), patch("sys.argv", ["job", "--dry-run"]), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(facebook_content_job.main(), 0)
        output = stdout.getvalue()
        self.assertIn("status: generated", output)
        self.assertIn("human_approval: missing", output)
        self.assertIn("publish_allowed: NO", output)
        self.publisher.assert_not_called()

    def test_production_entry_is_fail_closed_by_default(self):
        defaults = {
            "topics_path": self.topics_path,
            "skill_answerer": lambda topic: "generated article",
            "reviewer": lambda topic, post: PASS_REVIEW,
            "publisher": self.publisher,
        }
        with patch.object(facebook_content_job, "production_config_errors", return_value=()), patch.dict(
            facebook_content_job.run_governed_publish.__kwdefaults__, defaults
        ):
            with patch.dict(os.environ, {"CONTENT_APPROVAL_STORE_PATH": ""}),                  self.assertRaises(facebook_content_job.ProductionConfigError):
                run_publish_once()  # no store, no publishing
            with patch.dict(os.environ, {"CONTENT_APPROVAL_STORE_PATH": str(Path(self.temp_dir.name) / "store.json")}):
                result = run_publish_once()
        self.assert_blocked(result)
        self.assertEqual(result.approval_state, "reviewed")

    def test_approval_required_is_a_successful_business_outcome(self):
        self.assertEqual(EXIT_CODES[JobStatus.APPROVAL_REQUIRED], 0)


class PublishEndpointApprovalTest(unittest.TestCase):
    def test_approval_required_is_reported_as_unpublished_safe_block(self):
        client = main.app.test_client()
        with patch.dict(os.environ, {"AI_TUTOR_CRON_SECRET": "test-secret"}), patch(
            "main.run_publish_once", return_value=ContentJobResult(JobStatus.APPROVAL_REQUIRED)
        ) as job:
            response = client.post(
                "/internal/jobs/facebook-publish",
                headers={"Authorization": "Bearer test-secret"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ok": True, "state": "approval_required", "published": False})
        job.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
