from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader


MODULE_STARTS = (
    (3, "文件管理"),
    (9, "瓦斯抄錶"),
    (17, "生活資訊"),
    (22, "住戶資訊"),
    (39, "社區公告"),
    (46, "公設預約"),
    (66, "社區投票"),
    (74, "社區報修"),
    (90, "首頁輪播"),
    (95, "組織管理"),
    (117, "訪客預約"),
    (138, "郵件包裹"),
    (149, "意見反映"),
    (157, "資產管理"),
    (179, "管理費"),
    (182, "維運管理"),
    (188, "績效評估"),
    (191, "租售管理"),
)

SIDE_HEADING = re.compile(r"(?:壹|貳|參)、?\s*(管理端|住戶端)操作說明")
SECTION_HEADING = re.compile(r"^(?:[一二三四五六七八九十百]+|[0-9]+)[、.．]\s*(.+)$")
NOISE_PREFIXES = ("TEL:", "ADD:", "通航國際股份有限公司")


def module_for_page(page: int) -> str:
    module = "封面與目錄"
    for start, name in MODULE_STARTS:
        if page < start:
            break
        module = name
    return module


def clean_text(text: str) -> str:
    lines = []
    for raw_line in text.replace("\u3000", " ").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line.isdigit() or line.startswith(NOISE_PREFIXES):
            continue
        lines.append(line)
    return "\n".join(lines)


def section_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = SECTION_HEADING.match(line)
        if match:
            return match.group(1).strip()
    return fallback


def build_index(source: Path) -> dict:
    reader = PdfReader(str(source))
    chunks = []
    current_module = "封面與目錄"
    current_side = "both"
    current_section = "封面與目錄"

    for page_number, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        module = module_for_page(page_number)
        if module != current_module:
            current_module = module
            current_side = "both"
            current_section = module

        side_match = SIDE_HEADING.search(text)
        if side_match:
            current_side = "management" if side_match.group(1) == "管理端" else "resident"

        current_section = section_from_text(text, current_section)
        chunks.append(
            {
                "id": f"fa-p{page_number:03d}",
                "text": text,
                "metadata": {
                    "module": module,
                    "section": current_section,
                    "page_start": page_number,
                    "page_end": page_number,
                    "user_side": current_side,
                    "source_file": source.as_posix(),
                },
            }
        )

    return {"version": 1, "source_file": source.as_posix(), "page_count": len(reader.pages), "chunks": chunks}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the isolated FA manual page index.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    index = build_index(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"indexed {index['page_count']} pages -> {args.output}")


if __name__ == "__main__":
    main()
