"""Local review ledger for generated cybersecurity learning assets.

The ledger never writes source PDFs or source_evidence. A decision applies only
to the exact generated payload hash; edits reset its effective state to pending.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "knowledge" / "processed"
CARDS = ROOT / "cards"
DECISIONS = {"accept": "reviewed", "revise": "revision_required", "reject": "rejected"}


class ReviewError(ValueError):
    pass


def digest(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def generated_payload(kind: str, item: Any) -> Any:
    if kind == "teaching":
        return item
    if kind == "chunk":
        return {key: value for key, value in item["teaching_interpretation"].items() if key != "review_status"}
    if kind in {"card", "question"}:
        return {key: value for key, value in item.items() if key != "review_status"}
    raise ReviewError("Only generated teaching, chunk interpretations, cards and questions can be reviewed")


def load_ledger(path: Path) -> list[dict[str, Any]]:
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError("Review ledger cannot be read") from exc
    if not isinstance(records, list):
        raise ReviewError("Review ledger must be a list")
    for record in records:
        if not isinstance(record, dict) or record.get("kind") not in {"teaching", "chunk", "card", "question"}:
            raise ReviewError("Invalid review target")
        if (not isinstance(record.get("asset_id"), str) or not record["asset_id"]
                or record.get("decision") not in DECISIONS
                or not isinstance(record.get("content_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record["content_sha256"]) is None
                or record.get("reviewed_content") is None
                or digest(record["reviewed_content"]) != record["content_sha256"]
                or not isinstance(record.get("reviewed_at"), str)
                or not record["reviewed_at"]):
            raise ReviewError("Invalid review decision metadata")
        if record["decision"] in {"revise", "reject"} and not str(record.get("note", "")).strip():
            raise ReviewError("Revision and rejection require a reviewer note")
        try:
            reviewed_at = datetime.fromisoformat(record["reviewed_at"])
        except ValueError as exc:
            raise ReviewError("Invalid review timestamp") from exc
        if reviewed_at.tzinfo is None or reviewed_at.utcoffset() != timezone.utc.utcoffset(None):
            raise ReviewError("Review timestamp must be UTC")
    return records


def effective_status(kind: str, asset_id: str, item: Any, records: list[dict[str, Any]]) -> str:
    current_hash = digest(generated_payload(kind, item))
    for record in reversed(records):
        if record["kind"] == kind and record["asset_id"] == asset_id:
            return DECISIONS[record["decision"]] if record["content_sha256"] == current_hash else "pending_review"
    return "pending_review"


def find_asset(kind: str, asset_id: str, processed: Path = PROCESSED, cards: Path = CARDS) -> Any:
    if kind not in {"teaching", "chunk", "card", "question"}:
        raise ReviewError("Canonical source evidence is not a review target")
    try:
        index = json.loads((processed / "chapter_index.json").read_text(encoding="utf-8"))
        for chapter in index:
            if kind == "teaching" and chapter["chapter_id"] == asset_id:
                return (processed / chapter["teaching_file"]).read_text(encoding="utf-8").strip()
            filename = {"chunk": chapter["chunk_file"], "question": chapter["question_file"],
                        "card": Path(chapter["card_file"]).name}.get(kind)
            if not filename:
                continue
            directory = cards if kind == "card" else processed
            for item in json.loads((directory / filename).read_text(encoding="utf-8")):
                key = {"chunk": "chunk_id", "card": "card_id", "question": "question_id"}[kind]
                if item[key] == asset_id:
                    return item
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReviewError("Generated asset cannot be read") from exc
    raise ReviewError("Generated asset not found")


def record_decision(kind: str, asset_id: str, decision: str, note: str = "",
                    processed: Path = PROCESSED, cards: Path = CARDS) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ReviewError("Decision must be accept, revise or reject")
    if decision in {"revise", "reject"} and not note.strip():
        raise ReviewError("Revision and rejection require a reviewer note")
    item = find_asset(kind, asset_id, processed, cards)
    path = processed / "review_decisions.json"
    records = load_ledger(path)
    payload = generated_payload(kind, item)
    record = {"kind": kind, "asset_id": asset_id, "decision": decision,
              "content_sha256": digest(payload), "reviewed_content": payload,
              "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "note": note.strip()}
    records.append(record)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Review generated iPAS Cybersecurity assets")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    decide = sub.add_parser("decide")
    for command in (show, decide):
        command.add_argument("kind", choices=["teaching", "chunk", "card", "question"])
        command.add_argument("asset_id")
    decide.add_argument("decision", choices=list(DECISIONS))
    decide.add_argument("--note", default="")
    args = parser.parse_args()
    try:
        if args.command == "show":
            item = find_asset(args.kind, args.asset_id)
            records = load_ledger(PROCESSED / "review_decisions.json")
            print(json.dumps({"status": effective_status(args.kind, args.asset_id, item, records),
                              "generated_asset": generated_payload(args.kind, item)}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(record_decision(args.kind, args.asset_id, args.decision, args.note),
                             ensure_ascii=False, indent=2))
    except ReviewError as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
