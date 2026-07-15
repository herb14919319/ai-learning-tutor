from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
DEFAULT_PROCESSED_DIR = ROOT / "knowledge" / "processed"
DEFAULT_CARDS_DIR = ROOT / "cards"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process(processed_dir: Path, cards_dir: Path) -> None:
    from skills.ipas_net_zero_planner.skill import IpasNetZeroPlannerSkill

    skill = IpasNetZeroPlannerSkill(processed_dir, cards_dir=cards_dir)
    chapters = skill.get_chapters()
    sources = skill.get_sources()["sources"]
    write_json(processed_dir / "chapter_index.json", chapters)
    write_json(processed_dir / "source_manifest.json", sources)
    print(f"indexed {len(chapters)} chapters and {sum(len(item['cards']) for item in chapters)} cards")


def main() -> None:
    parser = argparse.ArgumentParser(description="Index processed iPAS net-zero Markdown chapters and cards.")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--cards-dir", type=Path, default=DEFAULT_CARDS_DIR)
    args = parser.parse_args()
    process(args.processed_dir, args.cards_dir)


if __name__ == "__main__":
    main()
