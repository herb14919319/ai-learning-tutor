from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False

from automation.content_review import (
    ContentReviewDecision,
    ContentReviewResult,
    ReviewIssue,
)
from automation.facebook_publisher import PublishResult, publish_page_post
from automation.source_review import review_content_with_sources


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOPICS_PATH = ROOT / "config" / "content_topics.json"
MAX_POST_LENGTH = 10_000
FALLBACK_MARKERS = (
    "抱歉，我剛剛查詢 skill 和一般 GPT 回答都遇到問題",
    "抱歉，目前系統發生異常",
    "抱歉，目前查詢時間較長",
)
SENSITIVE_PATTERN = re.compile(
    r"(?i)(traceback \(most recent call last\)|authorization\s*:\s*bearer|"
    r"access[_ -]?token\s*[:=]|api[_ -]?key\s*[:=]|\bsk-[a-z0-9_-]{12,}|"
    r"\bEAA[a-z0-9]{20,})"
)


class JobStatus(str, Enum):
    GENERATED = "generated"
    VALIDATION_FAILED = "validation_failed"
    REVIEW_REJECTED = "review_rejected"
    REVIEW_UNCERTAIN = "review_uncertain"
    PUBLISH_FAILED = "publish_failed"
    PUBLISHED = "published"


EXIT_CODES = {
    JobStatus.GENERATED: 0,
    JobStatus.PUBLISHED: 0,
    JobStatus.REVIEW_REJECTED: 1,
    JobStatus.REVIEW_UNCERTAIN: 1,
    JobStatus.VALIDATION_FAILED: 3,
    JobStatus.PUBLISH_FAILED: 4,
}
CONFIG_ERROR_EXIT_CODE = 2


def production_config_errors(environment: dict[str, str] | None = None) -> tuple[str, ...]:
    """Check presence only; never contact a model, source, or Facebook."""
    env = environment if environment is not None else os.environ
    required = (
        "MESSENGER_PAGE_ACCESS_TOKEN",
        "MESSENGER_PAGE_ID",
        "MESSENGER_API_VERSION",
        "MODEL_PROVIDER",
    )
    errors = [f"{name} is not configured" for name in required if not env.get(name, "").strip()]
    provider = env.get("MODEL_PROVIDER", "").strip().lower()
    credential = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }.get(provider)
    if provider and credential is None:
        errors.append("MODEL_PROVIDER must be openai, gemini, or deepseek")
    elif credential and not env.get(credential, "").strip():
        errors.append(f"{credential} is not configured")
    return tuple(errors)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContentJobResult:
    status: JobStatus
    topic: str | None = None
    post: str | None = None
    post_id: str | None = None
    errors: tuple[str, ...] = ()
    validation: ValidationResult | None = None
    review: ContentReviewResult | None = None

    @property
    def publish_allowed(self) -> bool:
        return bool(
            self.validation
            and self.validation.valid
            and self.review
            and self.review.decision is ContentReviewDecision.PASS
        )


def load_topics(path: Path = DEFAULT_TOPICS_PATH) -> list[str]:
    with path.open(encoding="utf-8") as topic_file:
        value = json.load(topic_file)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Topic pool must be a JSON array of strings")
    return value


def select_topic(
    topics: Sequence[str],
    chooser: Callable[[Sequence[str]], str] = random.choice,
) -> str:
    if not topics:
        raise ValueError("Topic pool is empty")
    return chooser(topics)


def answer_with_hungyi_skill(topic: str) -> str:
    """Invoke the canonical Hung-yi Lee skill registered by AI Learning Tutor."""
    from skills.registry import get_skill

    skill = get_skill("hungyi_lee")
    if skill is None:
        raise RuntimeError("Hung-yi Lee skill is unavailable")
    return skill.answer(topic)


def format_facebook_post(topic: str, skill_answer: str) -> str:
    return (
        "🤖 AI Learning Tutor｜本週 AI 小教室\n\n"
        f"{topic.strip()}\n\n"
        f"{skill_answer.strip()}\n\n"
        "#AI學習助教 #人工智慧 #AI學習"
    )


def _configured_secret_values() -> tuple[str, ...]:
    names = (
        "MESSENGER_PAGE_ACCESS_TOKEN",
        "MESSENGER_APP_SECRET",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "LINE_CHANNEL_ACCESS_TOKEN",
        "LINE_CHANNEL_SECRET",
    )
    return tuple(value for name in names if len(value := os.getenv(name, "")) >= 8)


def validate_post(topic: str, skill_answer: str, post: str) -> ValidationResult:
    errors: list[str] = []
    if not topic.strip():
        errors.append("topic is empty")
    if not skill_answer.strip():
        errors.append("skill answer is empty")
    if any(marker in skill_answer for marker in FALLBACK_MARKERS):
        errors.append("skill returned a known fallback response")
    if not post.strip():
        errors.append("generated post is empty")
    if len(post) > MAX_POST_LENGTH:
        errors.append(f"generated post exceeds {MAX_POST_LENGTH} characters")

    combined = "\n".join((topic, skill_answer, post))
    if SENSITIVE_PATTERN.search(combined):
        errors.append("generated content contains a secret or debug-trace marker")
    elif any(secret in combined for secret in _configured_secret_values()):
        errors.append("generated content contains a configured secret")
    return ValidationResult(not errors, tuple(errors))


def generate_post(
    *,
    topics_path: Path = DEFAULT_TOPICS_PATH,
    topic_selector: Callable[[Sequence[str]], str] = random.choice,
    skill_answerer: Callable[[str], str] = answer_with_hungyi_skill,
) -> ContentJobResult:
    try:
        topic = select_topic(load_topics(topics_path), topic_selector)
    except (OSError, ValueError, json.JSONDecodeError):
        return ContentJobResult(
            JobStatus.VALIDATION_FAILED,
            errors=("topic pool could not provide a topic",),
            validation=ValidationResult(False, ("topic pool could not provide a topic",)),
        )

    if not topic.strip():
        return ContentJobResult(
            JobStatus.VALIDATION_FAILED,
            topic=topic,
            errors=("topic is empty",),
            validation=ValidationResult(False, ("topic is empty",)),
        )

    try:
        skill_answer = skill_answerer(topic)
    except Exception:
        return ContentJobResult(
            JobStatus.VALIDATION_FAILED,
            topic=topic,
            errors=("Hung-yi Lee skill execution failed",),
            validation=ValidationResult(False, ("Hung-yi Lee skill execution failed",)),
        )

    skill_answer = skill_answer if isinstance(skill_answer, str) else ""
    post = format_facebook_post(topic, skill_answer)
    validation = validate_post(topic, skill_answer, post)
    if not validation.valid:
        return ContentJobResult(
            JobStatus.VALIDATION_FAILED,
            topic=topic,
            post=post,
            errors=validation.errors,
            validation=validation,
        )
    return ContentJobResult(
        JobStatus.GENERATED,
        topic=topic,
        post=post,
        validation=validation,
    )


def run_job(
    *,
    publish: bool = False,
    topics_path: Path = DEFAULT_TOPICS_PATH,
    topic_selector: Callable[[Sequence[str]], str] = random.choice,
    skill_answerer: Callable[[str], str] = answer_with_hungyi_skill,
    reviewer: Callable[[str, str], ContentReviewResult] = review_content_with_sources,
    publisher: Callable[[str], PublishResult] = publish_page_post,
) -> ContentJobResult:
    generated = generate_post(
        topics_path=topics_path,
        topic_selector=topic_selector,
        skill_answerer=skill_answerer,
    )
    if generated.status is not JobStatus.GENERATED:
        return generated

    try:
        review = reviewer(generated.topic or "", generated.post or "")
    except Exception:
        review = ContentReviewResult(
            ContentReviewDecision.UNCERTAIN,
            (ReviewIssue("review result", "Reviewer execution failed.", "high"),),
            "The reviewer failed; publication is blocked.",
        )

    if not isinstance(review, ContentReviewResult):
        review = ContentReviewResult(
            ContentReviewDecision.UNCERTAIN,
            (ReviewIssue("review result", "Reviewer returned an invalid result.", "high"),),
            "The reviewer result was invalid; publication is blocked.",
        )

    if review.decision is ContentReviewDecision.REJECT:
        return ContentJobResult(
            JobStatus.REVIEW_REJECTED,
            topic=generated.topic,
            post=generated.post,
            validation=generated.validation,
            review=review,
        )
    if review.decision is not ContentReviewDecision.PASS:
        return ContentJobResult(
            JobStatus.REVIEW_UNCERTAIN,
            topic=generated.topic,
            post=generated.post,
            validation=generated.validation,
            review=review,
        )
    if not publish:
        return ContentJobResult(
            JobStatus.GENERATED,
            topic=generated.topic,
            post=generated.post,
            validation=generated.validation,
            review=review,
        )

    try:
        published = publisher(generated.post or "")
    except Exception:
        published = PublishResult(False, error="Facebook Page publication failed")
    if not published.success:
        return ContentJobResult(
            JobStatus.PUBLISH_FAILED,
            topic=generated.topic,
            post=generated.post,
            errors=(published.error or "Facebook Page publication failed",),
            validation=generated.validation,
            review=review,
        )
    return ContentJobResult(
        JobStatus.PUBLISHED,
        topic=generated.topic,
        post=generated.post,
        post_id=published.post_id,
        validation=generated.validation,
        review=review,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or publish one AI Learning Tutor Page post")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Generate and print only (default)")
    mode.add_argument("--publish", action="store_true", help="Publish through the Meta Graph API")
    mode.add_argument("--check-config", action="store_true", help="Validate production configuration only")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    args = _parse_args()
    if args.check_config or args.publish:
        config_errors = production_config_errors()
        if config_errors:
            for error in config_errors:
                print(f"configuration_error: {error}")
            return CONFIG_ERROR_EXIT_CODE
        if args.check_config:
            print("production_configuration: valid")
            return 0
    result = run_job(publish=args.publish)
    print(f"status: {result.status.value}")
    if result.topic:
        print(f"topic: {result.topic}")
    if result.post:
        print("\n--- Facebook post ---\n")
        print(result.post)
    if result.validation:
        print(f"\ndeterministic_validation: {'pass' if result.validation.valid else 'fail'}")
    if result.review:
        print(f"review_decision: {result.review.decision.value}")
        print(f"review_summary: {result.review.summary}")
        for issue in result.review.issues:
            print(f"review_issue[{issue.severity}]: {issue.claim} — {issue.reason}")
        for claim in result.review.verified_claims:
            print(f"verification_claim[{claim.claim_id}]: {claim.text}")
        for source in result.review.sources_used:
            print(f"official_source[{source.authority}]: {source.name} — {source.url}")
        for evidence in result.review.evidence:
            print(
                f"evidence[{evidence.claim_id}]: {evidence.verdict.value} — "
                f"{evidence.source_name or 'no registered source'} — {evidence.reason}"
            )
            if evidence.excerpt:
                print(f"evidence_excerpt: {evidence.excerpt}")
    print(f"publish_allowed: {'YES' if result.publish_allowed else 'NO'}")
    if result.post_id:
        print(f"\npost_id: {result.post_id}")
    for error in result.errors:
        print(f"error: {error}")
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
