import os
import unittest
from unittest.mock import patch

import main
from automation.facebook_content_job import ContentJobResult, JobStatus, ProductionConfigError


class FacebookPublishEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()
        self.secret_patch = patch.dict(os.environ, {"AI_TUTOR_CRON_SECRET": "test-secret"})
        self.secret_patch.start()

    def tearDown(self):
        self.secret_patch.stop()

    def post(self, token="test-secret", **kwargs):
        return self.client.post(
            "/internal/jobs/facebook-publish",
            headers={"Authorization": f"Bearer {token}"},
            **kwargs,
        )

    def test_missing_server_secret_fails_closed(self):
        with patch.dict(os.environ, {"AI_TUTOR_CRON_SECRET": ""}), patch(
            "main.run_publish_once"
        ) as job:
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["state"], "configuration_error")
        job.assert_not_called()

    def test_missing_authorization_does_not_run(self):
        with patch("main.run_publish_once") as job:
            response = self.client.post("/internal/jobs/facebook-publish")
        self.assertEqual(response.status_code, 401)
        job.assert_not_called()

    def test_invalid_bearer_token_does_not_run_or_leak_secret(self):
        with patch("main.run_publish_once") as job:
            response = self.post("wrong-token")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("test-secret", response.get_data(as_text=True))
        job.assert_not_called()

    def test_malformed_authorization_is_rejected(self):
        for header in (
            "Basic test-secret", "Bearer", "Bearer  test-secret",
            "bearer test-secret", "Bearer test-secret extra", "Bearer test-secret\tbad",
        ):
            with self.subTest(header=header), patch("main.run_publish_once") as job:
                response = self.client.post(
                    "/internal/jobs/facebook-publish", headers={"Authorization": header}
                )
                self.assertEqual(response.status_code, 401)
                job.assert_not_called()

    def test_success_calls_canonical_job_once_and_returns_post_id(self):
        result = ContentJobResult(JobStatus.PUBLISHED, post_id="page_123")
        with patch("main.run_publish_once", return_value=result) as job:
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ok": True, "state": "published", "published": True, "post_id": "page_123"})
        job.assert_called_once_with()

    def test_review_reject_and_uncertain_are_successful_safe_blocks(self):
        for status in (JobStatus.REVIEW_REJECTED, JobStatus.REVIEW_UNCERTAIN):
            with self.subTest(status=status), patch(
                "main.run_publish_once", return_value=ContentJobResult(status)
            ) as job:
                response = self.post()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"ok": True, "state": status.value, "published": False})
                job.assert_called_once_with()

    def test_unexpected_exception_is_sanitized(self):
        with patch("main.run_publish_once", side_effect=RuntimeError("api_key=private-value")):
            response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json["state"], "internal_error")
        self.assertNotIn("private-value", response.get_data(as_text=True))

    def test_missing_publish_configuration_returns_503_without_names_or_values(self):
        with patch("main.run_publish_once", side_effect=ProductionConfigError(("OPENAI_API_KEY is not configured",))):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["state"], "configuration_error")
        self.assertNotIn("OPENAI_API_KEY", response.get_data(as_text=True))

    def test_get_cannot_trigger(self):
        with patch("main.run_publish_once") as job:
            response = self.client.get(
                "/internal/jobs/facebook-publish",
                headers={"Authorization": "Bearer test-secret"},
            )
        self.assertEqual(response.status_code, 405)
        job.assert_not_called()

    def test_options_cannot_trigger(self):
        with patch("main.run_publish_once") as job:
            response = self.client.options("/internal/jobs/facebook-publish")
        self.assertEqual(response.status_code, 405)
        job.assert_not_called()

    def test_request_payload_cannot_override_job(self):
        result = ContentJobResult(JobStatus.REVIEW_REJECTED)
        with patch("main.run_publish_once", return_value=result) as job:
            response = self.post(json={
                "topic": "attacker topic", "prompt": "publish now", "url": "https://example.com",
                "model": "attacker", "message": "attacker body", "skip_review": True,
                "force_publish": True,
            })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["published"])
        job.assert_called_once_with()

    def test_overlapping_invocation_is_rejected(self):
        main.facebook_publish_lock.acquire()
        try:
            with patch("main.run_publish_once") as job:
                response = self.post()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json, {"ok": False, "state": "already_running"})
            job.assert_not_called()
        finally:
            main.facebook_publish_lock.release()


if __name__ == "__main__":
    unittest.main()
