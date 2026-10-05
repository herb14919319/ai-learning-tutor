"""Persistent human-approval store for Facebook posts: draft → reviewed → approved → published.

One JSON file holds every record. On Render it must live on a Persistent Disk
attached to the web service (CONTENT_APPROVAL_STORE_PATH); the service
filesystem is otherwise ephemeral and a disk cannot be shared with a Render
Cron Job, so scheduled runs use the HTTP trigger and operators run the CLI in
the web service shell.

The exact post text and its SHA-256 are stored. The hash is authoritative:
approval is for one hash, and a record whose text no longer matches its hash
can never publish.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path


STORE_PATH_ENV = "CONTENT_APPROVAL_STORE_PATH"
SCHEMA_VERSION = 1
STATES = ("draft", "reviewed", "approved", "published")
LOCK_TIMEOUT_SECONDS = 10.0
STALE_LOCK_SECONDS = 60.0


class ApprovalStoreError(RuntimeError):
    """The store file cannot be read, written or trusted."""


class ApprovalTransitionError(ValueError):
    """The requested state change is not allowed."""


def post_sha256(post: str) -> str:
    return hashlib.sha256(post.encode("utf-8")).hexdigest()


def content_id_for(post: str) -> str:
    return f"fb-{post_sha256(post)[:16]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ContentRecord:
    content_id: str
    topic: str
    post: str
    post_sha256: str
    state: str
    review_decision: str
    created_at: str
    reviewed_at: str | None = None
    approved_at: str | None = None
    published_at: str | None = None
    post_id: str | None = None
    note: str | None = None

    @property
    def content_intact(self) -> bool:
        return post_sha256(self.post) == self.post_sha256 and content_id_for(self.post) == self.content_id


class ApprovalStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self._thread_lock = threading.Lock()

    # --- persistence -------------------------------------------------------

    def _acquire_file_lock(self) -> None:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ApprovalStoreError("Approval store directory cannot be created") from exc
        while True:
            try:
                descriptor = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(descriptor)
                return
            except FileExistsError:
                try:
                    if time.time() - self._lock_path.stat().st_mtime > STALE_LOCK_SECONDS:
                        self._lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise ApprovalStoreError("Approval store is locked by another process")
                time.sleep(0.05)
            except OSError as exc:
                raise ApprovalStoreError("Approval store lock cannot be created") from exc

    def _read(self) -> dict[str, ContentRecord]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("records"), dict):
                raise ApprovalStoreError("Approval store has an unsupported format")
            records = {key: ContentRecord(**value) for key, value in payload["records"].items()}
        except ApprovalStoreError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            raise ApprovalStoreError("Approval store cannot be read") from exc
        if any(key != record.content_id or record.state not in STATES for key, record in records.items()):
            raise ApprovalStoreError("Approval store contains an invalid record")
        return records

    def _write(self, records: dict[str, ContentRecord]) -> None:
        payload = {"schema_version": SCHEMA_VERSION, "records": {key: asdict(value) for key, value in records.items()}}
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise ApprovalStoreError("Approval store cannot be written") from exc

    def _update(self, change):
        with self._thread_lock:
            self._acquire_file_lock()
            try:
                records = self._read()
                result, changed = change(records)
                if changed:
                    self._write(records)
                return result
            finally:
                self._lock_path.unlink(missing_ok=True)

    # --- queries -----------------------------------------------------------

    def get(self, content_id: str) -> ContentRecord | None:
        with self._thread_lock:
            return self._read().get(content_id)

    def list_records(self) -> list[ContentRecord]:
        with self._thread_lock:
            return sorted(self._read().values(), key=lambda record: (record.created_at, record.content_id))

    def next_approved(self) -> ContentRecord | None:
        approved = [record for record in self.list_records() if record.state == "approved"]
        return min(approved, key=lambda record: (record.approved_at or "", record.content_id), default=None)

    # --- transitions -------------------------------------------------------

    def record_draft(self, topic: str, post: str, review_decision: str) -> ContentRecord:
        """Store a generated post as a draft; the same text again returns the existing record unchanged."""
        content_id = content_id_for(post)

        def change(records):
            if content_id in records:
                return records[content_id], False
            record = ContentRecord(content_id=content_id, topic=topic, post=post, post_sha256=post_sha256(post),
                                   state="draft", review_decision=review_decision, created_at=utc_now())
            records[content_id] = record
            return record, True

        return self._update(change)

    def mark_reviewed(self, content_id: str, note: str | None = None) -> ContentRecord:
        """draft → reviewed, only after the automated content review passed. Idempotent afterwards."""

        def change(records):
            record = self._require(records, content_id)
            if record.state != "draft":
                return record, False
            if record.review_decision != "pass":
                raise ApprovalTransitionError("Only drafts that passed the automated content review can be marked reviewed")
            records[content_id] = replace(record, state="reviewed", reviewed_at=utc_now(), note=note or record.note)
            return records[content_id], True

        return self._update(change)

    def approve(self, content_id: str, expected_sha256: str, note: str | None = None) -> ContentRecord:
        """reviewed → approved for exactly the content with expected_sha256. Idempotent for the same hash."""

        def change(records):
            record = self._require(records, content_id)
            if not record.content_intact:
                raise ApprovalTransitionError("Stored content no longer matches its hash")
            if (expected_sha256 or "").strip().lower() != record.post_sha256:
                raise ApprovalTransitionError("Approval hash does not match the stored content")
            if record.state in ("approved", "published"):
                return record, False
            if record.state != "reviewed":
                raise ApprovalTransitionError("Only reviewed content can be approved")
            records[content_id] = replace(record, state="approved", approved_at=utc_now(), note=note or record.note)
            return records[content_id], True

        return self._update(change)

    def mark_published(self, content_id: str, post_id: str | None) -> ContentRecord:
        """approved → published. Idempotent; never re-opens published content."""

        def change(records):
            record = self._require(records, content_id)
            if record.state == "published":
                return record, False
            if record.state != "approved":
                raise ApprovalTransitionError("Only approved content can be marked published")
            records[content_id] = replace(record, state="published", published_at=utc_now(), post_id=post_id)
            return records[content_id], True

        return self._update(change)

    @staticmethod
    def _require(records: dict[str, ContentRecord], content_id: str) -> ContentRecord:
        record = records.get(content_id)
        if record is None:
            raise ApprovalTransitionError(f"Unknown content id: {content_id}")
        return record


def store_from_env(environment: dict[str, str] | None = None) -> ApprovalStore | None:
    env = environment if environment is not None else os.environ
    path = env.get(STORE_PATH_ENV, "").strip()
    return ApprovalStore(Path(path)) if path else None
