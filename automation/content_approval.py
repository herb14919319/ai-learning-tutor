"""Operator CLI for the Facebook post approval store.

Run it where the store lives (on Render: the web service shell, with
CONTENT_APPROVAL_STORE_PATH pointing at the persistent disk):

    python -m automation.content_approval list
    python -m automation.content_approval show <content_id>
    python -m automation.content_approval status <content_id>
    python -m automation.content_approval mark-reviewed <content_id> [--note TEXT]
    python -m automation.content_approval approve <content_id> --sha256 <post_sha256> [--note TEXT]

Approval names the exact post hash printed by `show`, so only the content
that was read can be approved. Publishing happens on the next scheduled run.
"""

from __future__ import annotations

import argparse
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False

from automation.approval_store import (
    STORE_PATH_ENV,
    ApprovalStoreError,
    ApprovalTransitionError,
    ContentRecord,
    store_from_env,
)


EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_NOT_CONFIGURED = 2
EXIT_STORE_ERROR = 5


def _summary(record: ContentRecord) -> str:
    return f"{record.content_id}\t{record.state}\t{record.created_at}\t{record.topic}"


def _details(record: ContentRecord) -> str:
    lines = [
        f"content_id: {record.content_id}",
        f"state: {record.state}",
        f"post_sha256: {record.post_sha256}",
        f"content_intact: {'yes' if record.content_intact else 'NO'}",
        f"automated_review: {record.review_decision}",
        f"topic: {record.topic}",
        f"created_at: {record.created_at}",
        f"reviewed_at: {record.reviewed_at or '-'}",
        f"approved_at: {record.approved_at or '-'}",
        f"published_at: {record.published_at or '-'}",
        f"post_id: {record.post_id or '-'}",
        f"note: {record.note or '-'}",
    ]
    return "\n".join(lines)


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Inspect and approve Facebook post drafts")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List stored posts")
    for name in ("show", "status"):
        commands.add_parser(name, help=f"{name} one post").add_argument("content_id")
    reviewed = commands.add_parser("mark-reviewed", help="draft → reviewed (automated review must have passed)")
    reviewed.add_argument("content_id")
    reviewed.add_argument("--note")
    approve = commands.add_parser("approve", help="reviewed → approved for the exact post hash")
    approve.add_argument("content_id")
    approve.add_argument("--sha256", required=True)
    approve.add_argument("--note")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    args = _parse_args(argv)
    store = store_from_env()
    if store is None:
        print(f"configuration_error: {STORE_PATH_ENV} is not configured")
        return EXIT_NOT_CONFIGURED
    try:
        if args.command == "list":
            for record in store.list_records():
                print(_summary(record))
            return EXIT_OK
        if args.command in ("show", "status"):
            record = store.get(args.content_id)
            if record is None:
                print(f"error: unknown content id: {args.content_id}")
                return EXIT_REFUSED
            if args.command == "status":
                print(record.state)
            else:
                print(_details(record))
                print("\n--- post ---\n")
                print(record.post)
            return EXIT_OK
        if args.command == "mark-reviewed":
            record = store.mark_reviewed(args.content_id, note=args.note)
        else:
            record = store.approve(args.content_id, args.sha256, note=args.note)
        print(f"{record.content_id}: {record.state}")
        return EXIT_OK
    except ApprovalTransitionError as exc:
        print(f"refused: {exc}")
        return EXIT_REFUSED
    except ApprovalStoreError as exc:
        print(f"approval_store_error: {exc}")
        return EXIT_STORE_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
