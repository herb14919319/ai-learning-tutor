from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "knowledge" / "source"
DEFAULT_OUTPUT_DIR = ROOT / "knowledge" / "processed"
EXPECTED_SOURCES = {
    "ipas_official_topics.docx": {
        "source_id": "SRC-CORE-001",
        "title": "iPAS 初級 AI 應用規劃師七大評鑑主題教學講義",
        "source_role": "core_outline",
        "version_date": None,
        "anchors": ("第 1 章 【L111】人工智慧概念", "1.5 臺灣在地 AI 法規與機構"),
        "notes": "作為七大章節主架構；文件自述依官方評鑑範圍編排，但本 Skill 不將課程講義視為官方法規或官方唯一標準。文件未標示可可靠辨識的版本日期。",
    },
    "ipas_generative_ai.docx": {
        "source_id": "SRC-GENAI-001",
        "title": "iPAS AI 應用規劃師（初級）科目二生成式 AI 應用與規劃完整教學講義（深化版）",
        "source_role": "detailed_reference",
        "version_date": "2026-05-04",
        "anchors": ("第 9 章 生成式 AI 風險管理與治理", "可解釋 AI"),
        "notes": "作為科目二、新技術、治理與 XAI 補充；不取代七大評鑑主題講義的章節架構。",
    },
    "ipas_exam_analysis_114_115.docx": {
        "source_id": "SRC-EXAM-001",
        "title": "iPAS 初級 AI 應用規劃師 114–115 年考古題分析報告",
        "source_role": "exam_analysis",
        "version_date": "2026-03-21",
        "anchors": ("【L11101】L111 人工智慧概念", "【L11102】L111 人工智慧概念"),
        "notes": "版本日期採報告涵蓋之最新考試日期；只用於題型、考點與名詞參考。MVP 題目均重新編寫，不標示為官方題目。",
    },
}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CHAPTER_REQUIRED_FIELDS = {
    "chapter_id",
    "lesson_code",
    "title",
    "order",
    "source_file",
    "status",
}
LEGACY_CHAPTER_FIELDS = {"topic_code", "processing_status"}
FORMAL_CHAPTERS = (
    {
        "chapter_id": "CH-01",
        "lesson_code": "L111",
        "title": "人工智慧概念",
        "order": 1,
        "source_file": "ch01_ai_concepts.md",
        "core_sections": [
            "1.1 AI 的能力範疇分類",
            "1.2 AI 應用領域與產業對應",
            "1.3 AI 治理三層人機監督模式",
            "1.4 可解釋 AI（XAI）四大技術",
            "1.5 臺灣在地 AI 法規與機構",
        ],
    },
    {
        "chapter_id": "CH-02",
        "lesson_code": "L112",
        "title": "資料處理與分析概念",
        "order": 2,
        "source_file": "ch02_data_processing_and_analysis.md",
        "core_sections": ["第 2 章 【L112】資料處理與分析概念"],
    },
    {
        "chapter_id": "CH-03",
        "lesson_code": "L113",
        "title": "機器學習概念",
        "order": 3,
        "source_file": "ch03_machine_learning_concepts.md",
        "core_sections": ["第 3 章 【L113】機器學習概念"],
    },
    {
        "chapter_id": "CH-04",
        "lesson_code": "L114",
        "title": "鑑別式 AI 與生成式 AI 概念",
        "order": 4,
        "source_file": "ch04_discriminative_and_generative_ai_concepts.md",
        "core_sections": ["第 4 章 【L114】鑑別式 AI 與生成式 AI 概念"],
    },
    {
        "chapter_id": "CH-05",
        "lesson_code": "L121",
        "title": "No-Code／Low-Code 概念",
        "order": 5,
        "source_file": "ch05_no_code_low_code_concepts.md",
        "core_sections": ["第 5 章 【L121】No Code / Low Code 概念"],
    },
    {
        "chapter_id": "CH-06",
        "lesson_code": "L122",
        "title": "生成式 AI 應用領域與工具使用",
        "order": 6,
        "source_file": "ch06_generative_ai_applications_and_tools.md",
        "core_sections": ["第 6 章 【L122】生成式 AI 應用領域與工具使用"],
    },
    {
        "chapter_id": "CH-07",
        "lesson_code": "L123",
        "title": "生成式 AI 導入評估規劃",
        "order": 7,
        "source_file": "ch07_generative_ai_adoption_evaluation_and_planning.md",
        "core_sections": ["第 7 章 【L123】生成式 AI 導入評估規劃"],
    },
)


def _element_text(element: ET.Element) -> str:
    text = "".join(node.text or "" for node in element.iter(f"{W}t"))
    return re.sub(r"\s+", " ", text).strip()


def read_docx(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise RuntimeError(f"無法解析 DOCX：{path.name}: {exc}") from exc

    paragraphs = []
    tables = []
    body = root.find(f"{W}body")
    if body is None:
        raise RuntimeError(f"DOCX 缺少 document body：{path.name}")
    for child in body:
        if child.tag == f"{W}p":
            text = _element_text(child)
            if text:
                paragraphs.append(text)
        elif child.tag == f"{W}tbl":
            rows = []
            for row in child.findall(f"{W}tr"):
                cells = [_element_text(cell) for cell in row.findall(f"{W}tc")]
                if any(cells):
                    rows.append(cells)
            if rows:
                tables.append(rows)
    return {
        "paragraphs": paragraphs,
        "tables": tables,
        "text": "\n".join(paragraphs),
        "file_size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def ref(source_id: str, section: str, locator: str) -> dict:
    return {"source_id": source_id, "section": section, "locator": locator}


def build_manifest(parsed: dict[str, dict], processed_at: str) -> list[dict]:
    items = []
    for filename, config in EXPECTED_SOURCES.items():
        doc = parsed[filename]
        missing_anchors = [anchor for anchor in config["anchors"] if anchor not in doc["text"]]
        status = "success" if not missing_anchors else "requires_review"
        notes = config["notes"]
        if missing_anchors:
            notes += " 缺少預期章節標記：" + "、".join(missing_anchors)
        items.append(
            {
                "source_id": config["source_id"],
                "filename": filename,
                "title": config["title"],
                "file_type": "docx",
                "file_size_bytes": doc["file_size_bytes"],
                "sha256": doc["sha256"],
                "source_role": config["source_role"],
                "version_date": config["version_date"],
                "processed_at": processed_at,
                "parse_status": status,
                "notes": notes,
            }
        )
    return items


def validate_chapter_index(chapters: object, processed_dir: Path) -> list[dict]:
    if not isinstance(chapters, list):
        raise ValueError("chapter_index 必須是 JSON 陣列。")
    if len(chapters) != len(FORMAL_CHAPTERS):
        raise ValueError(f"chapter_index 必須包含 {len(FORMAL_CHAPTERS)} 章，實際為 {len(chapters)} 章。")

    validated = []
    for position, item in enumerate(chapters, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"chapter_index 第 {position} 筆必須是物件。")
        missing = sorted(CHAPTER_REQUIRED_FIELDS - item.keys())
        if missing:
            raise ValueError(f"chapter_index 第 {position} 筆缺少欄位：{'、'.join(missing)}。")
        legacy = sorted(LEGACY_CHAPTER_FIELDS & item.keys())
        if legacy:
            raise ValueError(f"chapter_index 第 {position} 筆包含舊欄位：{'、'.join(legacy)}。")
        for field in ("chapter_id", "lesson_code", "title", "source_file", "status"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError(f"chapter_index 第 {position} 筆的 {field} 必須是非空字串。")
        if not isinstance(item["order"], int) or isinstance(item["order"], bool):
            raise ValueError(f"chapter_index 第 {position} 筆的 order 必須是整數。")
        validated.append(dict(item))

    for field in ("chapter_id", "lesson_code", "order", "source_file"):
        values = [item[field] for item in validated]
        normalized = [value.casefold() if isinstance(value, str) else value for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"chapter_index 欄位 {field} 不可重複。")

    expected_orders = list(range(1, len(FORMAL_CHAPTERS) + 1))
    actual_orders = [item["order"] for item in validated]
    if actual_orders != expected_orders:
        raise ValueError(f"chapter_index 順序必須為 {expected_orders}，實際為 {actual_orders}。")

    for item, expected in zip(validated, FORMAL_CHAPTERS, strict=True):
        for field in ("chapter_id", "lesson_code", "title", "order", "source_file"):
            if item[field] != expected[field]:
                raise ValueError(
                    f"chapter_index {expected['chapter_id']} 的 {field} 必須為 {expected[field]!r}，"
                    f"實際為 {item[field]!r}。"
                )
        if item["status"] != "completed":
            raise ValueError(f"chapter_index {item['chapter_id']} 的 status 必須為 completed。")
        source_file = str(item["source_file"])
        if Path(source_file).name != source_file or Path(source_file).suffix.casefold() != ".md":
            raise ValueError(f"chapter_index {item['chapter_id']} 的 source_file 必須是安全的 Markdown 檔名。")
        if not (processed_dir / source_file).is_file():
            raise FileNotFoundError(
                f"chapter_index {item['chapter_id']} 缺少正式教材 Markdown：{source_file}；未覆寫既有索引。"
            )
    return validated


def build_chapter_index(processed_dir: Path = DEFAULT_OUTPUT_DIR) -> list[dict]:
    result = []
    for metadata in FORMAL_CHAPTERS:
        chapter_id = metadata["chapter_id"]
        lesson_code = metadata["lesson_code"]
        title = metadata["title"]
        core_sections = metadata["core_sections"]
        if lesson_code == "L111":
            source_ids = ["SRC-CORE-001", "SRC-EXAM-001", "SRC-GENAI-001"]
            source_sections = {
                "SRC-CORE-001": core_sections,
                "SRC-EXAM-001": ["【L11101】AI的定義與分類", "【L11102】AI治理概念"],
                "SRC-GENAI-001": ["9-6 國際與國內 AI 治理框架", "9-7 風險溯源與透明度"],
            }
            references = [
                "SRC-CORE-001：第 1 章 1.1–1.5（主要依據）",
                "SRC-EXAM-001：第六章 L11101–L11102（題型與名詞補充）",
                "SRC-GENAI-001：第 9 章 9-6–9-7（治理與 XAI 補充）",
            ]
        else:
            source_ids = ["SRC-CORE-001"]
            source_sections = {"SRC-CORE-001": core_sections}
            references = [f"SRC-CORE-001：{core_sections[0]}"]
        result.append(
            {
                "chapter_id": chapter_id,
                "lesson_code": lesson_code,
                "title": title,
                "order": metadata["order"],
                "source_file": metadata["source_file"],
                "source_ids": source_ids,
                "source_sections": source_sections,
                "page_or_section_reference": references,
                "status": "completed",
            }
        )
    return validate_chapter_index(result, Path(processed_dir))


def build_knowledge() -> list[dict]:
    core = "SRC-CORE-001"
    exam = "SRC-EXAM-001"
    gen = "SRC-GENAI-001"
    base = {"topic_code": "L111", "review_status": "pending_review"}
    items = [
        {
            **base,
            "knowledge_id": "L111-K001",
            "title": "AI 定義",
            "definition": "本 Skill 依教材的能力分類與應用領域所作的綜合整理：人工智慧是涵蓋多種方法的上位概念，用來描述電腦系統執行辨識、理解、預測、決策或內容生成等任務。這不是教材逐字提供的單一定義。",
            "plain_explanation": "在本教材脈絡中，AI 是讓電腦能看、聽、讀、判斷或產生內容的一大類技術；它不等於某一個模型，也不只包含生成式 AI。",
            "key_points": ["AI 是上位概念，應用可包含 NLP、電腦視覺、語音辨識、推薦與預測。", "現有實務系統通常針對特定任務。"],
            "common_confusions": ["教材沒有在 L111 直接給出單一句的 AI 總定義，本項為依能力分類與應用領域整理的綜合定義。", "AI 不等同機器學習；機器學習是實作 AI 的方法之一。"],
            "source_references": [ref(core, "第 1 章章節概述與 1.1–1.2", "paragraphs 26–48; tables 0–1"), ref(exam, "L11101 AI 的定義與分類", "paragraphs 2096–2125")],
            "requires_review": True,
        },
        {
            **base,
            "knowledge_id": "L111-K002",
            "title": "弱 AI、強 AI、AGI、ASI",
            "definition": "主講義把弱 AI、Strong AI、AGI、ASI 列成四個層次：Strong AI 是理論上具類人跨任務認知能力，AGI 是能執行任何人類智能任務，ASI 則在所有領域超越人類；考古分析報告另將 Strong AI 稱為『通用 AI（廣義）』，因此 Strong AI 與 AGI 的邊界在兩份教材中並不一致。",
            "plain_explanation": "兩份教材一致把弱 AI 視為特定任務的專才、ASI 視為全面超越人類；但 Strong AI 與 AGI 有時分成相鄰層級，有時部分重疊，不能當成毫無爭議的唯一分類。",
            "key_points": ["題目出現單一任務、不能遷移，通常指弱 AI。", "主講義區分 Strong AI 與 AGI；考古分析報告則讓兩者概念部分重疊。", "ASI 的關鍵字是全面超越人類。"],
            "common_confusions": ["主講義把強 AI 與 AGI 排成相鄰層級；考古分析則說強 AI 也可稱通用 AI（廣義）。兩者界線需依題幹與教材用語判斷。"],
            "source_references": [ref(core, "1.1 AI 的能力範疇分類", "paragraphs 30–38; table 0"), ref(exam, "L11101 AI 的定義與分類", "paragraphs 2097–2115")],
            "conflict": {"status": "requires_review", "detail": "Strong AI 與 AGI 在兩份教材中的分層／同義關係措辭不同。"},
            "requires_review": True,
        },
        {
            **base,
            "knowledge_id": "L111-K003",
            "title": "傳統 AI、機器學習與深度學習",
            "definition": "教材可直接確認深度學習是機器學習的子集，並以多層神經網路為基礎；生成式 AI 講義則把『傳統 AI』概括為偏向分類、預測或判斷的系統。教材沒有直接把『傳統 AI』定義成規則式 AI，也沒有在這些段落完整定義 AI 與機器學習的集合關係。",
            "plain_explanation": "最有教材依據的關係是『深度學習屬於機器學習』。常見教科書也會用 AI ⊃ 機器學習 ⊃ 深度學習來記，但本批教材沒有在引用段落完整畫出這個包含關係，所以仍需人工確認。",
            "key_points": ["教材直接支持：深度學習是機器學習的重要子集。", "生成式 AI 常奠基於深度學習，但深度學習不只用於生成。", "本教材中的『傳統 AI』偏向與生成式 AI 對照的分類、預測或判斷，不應直接等同規則式 AI。"],
            "common_confusions": ["不要把 AI、機器學習、深度學習當成完全同義詞。", "不要把『傳統 AI』一律改寫成『規則式 AI』；教材沒有支持這個唯一對應。", "AI ⊃ 機器學習 ⊃ 深度學習是常見整理框架，但本項只有『機器學習 ⊃ 深度學習』獲引用段落直接陳述。"],
            "source_references": [ref(core, "3.1 學習模式六大家族與 3.6 神經網路與深度學習基礎", "paragraphs 309–317 and 376–393; table 12"), ref(gen, "2-1 生成式 AI 的定義與本質、2-2 鑑別式 AI vs. 生成式 AI", "paragraphs 53–58; tables 6–7")],
            "requires_review": True,
        },
        {
            **base,
            "knowledge_id": "L111-K004",
            "title": "AI 應用領域",
            "definition": "常見 AI 應用可依輸入與任務分為自然語言處理、電腦視覺、語音辨識、推薦系統、預測性維護，以及醫療、金融與交通等產業應用。",
            "plain_explanation": "先看 AI 處理什麼：圖像多半是 CV，語音轉文字是 ASR，文字理解是 NLP，依喜好排序是推薦，預先找設備異常是預測性維護。",
            "key_points": ["影像辨識、物件偵測、分割屬電腦視覺。", "語意理解、生成、翻譯屬 NLP。", "設備故障預警是智慧製造常見的預測性維護。"],
            "common_confusions": ["題目常故意把正確技術配到錯誤產業。", "ASR 著重語音轉文字；NLP 著重語言理解與生成。"],
            "source_references": [ref(core, "1.2 AI 應用領域與產業對應", "paragraphs 40–48; table 1"), ref(exam, "L11101 Computer Vision / NLP", "paragraphs 2117–2125")],
        },
        {
            **base,
            "knowledge_id": "L111-K005",
            "title": "AI 治理基本概念",
            "definition": "AI 治理是在 AI 全生命週期建立政策、流程、組織責任與監督機制，使系統符合倫理、法規與組織要求。",
            "plain_explanation": "治理是組織如何管理 AI 的制度層：誰負責、怎麼監督、風險怎麼處理、如何查核是否符合規範。倫理提供價值原則，風險管理處理風險辨識與控制，法規遵循確認適用要求；三者與治理相關，但不是彼此同義。",
            "key_points": ["治理涵蓋設計、開發、部署、使用到退役。", "人機監督與可解釋性都是治理手段。", "高風險應用通常需要更強的人工監督、透明度與稽核。"],
            "common_confusions": ["治理不只是資安，也包含當責、公平、可靠、隱私與可解釋性。", "教材沒有另行提供 AI 倫理的完整正式定義；倫理、風險管理、法遵與治理的界線屬依各章內容作的整理，仍需人工確認。", "課程講義不是官方法規或唯一標準；涉及現行法規時需另行查核最新官方資訊。"],
            "source_references": [ref(exam, "L11102 AI Governance", "paragraphs 2127–2131"), ref(core, "第 1 章章節概述與 1.3–1.5", "paragraphs 26–82"), ref(gen, "9-1–9-7 風險管理、治理框架與透明度", "paragraphs 269–288; tables 54–60")],
            "requires_review": True,
        },
        {
            **base,
            "knowledge_id": "L111-K006",
            "title": "HITL（Human-in-the-loop）",
            "definition": "依本教材，AI 的每個關鍵決策都需要人類審核、批准或介入後才能繼續。",
            "plain_explanation": "AI 提建議，但關鍵一步一定要人點頭。",
            "key_points": ["人類角色是決策者。", "常見線索是逐筆、每個關鍵決策、最終確認。", "適合醫療診斷、貸款核准等高風險情境。"],
            "common_confusions": ["不是只看報表或異常才介入；那更接近 HOTL。"],
            "source_references": [ref(core, "1.3 AI 治理三層人機監督模式", "paragraphs 50–58; table 2"), ref(exam, "L11102 HITL", "paragraphs 2133–2136")],
        },
        {
            **base,
            "knowledge_id": "L111-K007",
            "title": "HOTL（Human-over-the-loop）",
            "definition": "依本教材，AI 可自主運行，人類進行日常監督，並在需要時介入或調整。",
            "plain_explanation": "AI 平常自己做，人類在旁監看，必要時踩煞車。",
            "key_points": ["人類角色是監督者。", "常見線索是日常監督、監控儀表板、必要時介入。", "介入頻率低於 HITL，但仍保有及時控制能力。"],
            "common_confusions": ["若人類只在重大故障後才接手，較接近 HOOTL。"],
            "source_references": [ref(core, "1.3 AI 治理三層人機監督模式", "paragraphs 50–58; table 2"), ref(exam, "L11102 HOTL", "paragraphs 2138–2141")],
        },
        {
            **base,
            "knowledge_id": "L111-K008",
            "title": "HOOTL（Human-out-of-the-loop）",
            "definition": "依本教材，AI 系統自主完成決策與執行，人類只在重大異常或事故時接管。",
            "plain_explanation": "平常完全自動，出了大事才找人。",
            "key_points": ["自動化程度最高。", "常見線索是完全自主、重大異常才介入。", "高風險情境使用時需要特別審慎的治理與失效保護。"],
            "common_confusions": ["『人在迴圈外』不代表系統完全不需治理、監控或事後責任。"],
            "source_references": [ref(core, "1.3 AI 治理三層人機監督模式", "paragraphs 50–58; table 2"), ref(exam, "L11102 HOOTL", "paragraphs 2143–2146")],
        },
        {
            **base,
            "knowledge_id": "L111-K009",
            "title": "可解釋 AI（XAI）",
            "definition": "XAI 是讓人能理解 AI 決策依據或行為的技術總稱，可包含模型本身可解釋，以及對黑盒模型做事後解釋的方法。",
            "plain_explanation": "XAI 讓 AI 不只給答案，也能提供人可理解的理由或影響因素。",
            "key_points": ["LIME 著重單一樣本附近的局部解釋。", "SHAP 將預測拆成各特徵的貢獻。", "反事實解釋回答『改變什麼會翻轉結果』。", "顯著性圖標示影像中影響判斷的區域。"],
            "common_confusions": ["XAI 不保證模型一定正確、公平或安全。", "顯著性圖主要對應影像，不是一般表格資料的萬用解釋法。"],
            "source_references": [ref(core, "1.4 可解釋 AI（XAI）四大技術", "paragraphs 60–68; table 3"), ref(exam, "L11102 XAI、LIME、SHAP、反事實、顯著性圖", "paragraphs 2153–2171"), ref(gen, "9-7 風險溯源與透明度", "paragraph 285")],
        },
        {
            **base,
            "knowledge_id": "L111-K010",
            "title": "L111 常見考試陷阱",
            "definition": "L111 題目常用相近術語、錯置產業、介入時機與過度延伸的治理敘述來製造干擾。",
            "plain_explanation": "先抓題幹關鍵字，再判斷能力範圍、資料型態、人何時介入，以及題目是否把治理效果說得太滿。",
            "key_points": ["特定任務、無法遷移通常指弱 AI。", "逐筆核准是 HITL；持續監督、必要介入是 HOTL；重大異常才接手是 HOOTL。", "『改什麼才會通過』是反事實解釋；『影像看哪裡』是顯著性圖。", "XAI 是解釋工具，不等於正確性保證。"],
            "common_confusions": ["不要只看產業名稱，要看實際輸入與任務。", "法規與機構資訊可能隨時間變動；本 MVP 不自動更新，也不把講義當成現行官方唯一標準。"],
            "source_references": [ref(core, "1.1–1.5 應試小技巧", "paragraphs 38, 48, 58, 68, 82"), ref(exam, "執行摘要 1.2–1.3 與 L111 題型分析", "paragraphs 20–27; L11101–L11102 entries")],
        },
    ]
    return items


def build_questions() -> list[dict]:
    core = "SRC-CORE-001"
    exam = "SRC-EXAM-001"
    q = []

    def add(number: int, question: str, options: dict, answer: str, explanation: str, refs: list, difficulty: str) -> None:
        q.append(
            {
                "question_id": f"L111-Q{number:03d}",
                "topic_code": "L111",
                "question": question,
                "options": options,
                "correct_answer": answer,
                "explanation": explanation,
                "source_references": refs,
                "difficulty": difficulty,
                "question_type": "single_choice_generated",
                "review_status": "pending_review",
                "authorship": "model_generated_from_materials",
            }
        )

    add(1, "一套系統只會辨識產線上的特定瑕疵，換到其他任務就不能直接使用。依能力範圍最適合歸類為何？", {"A": "弱 AI", "B": "強 AI", "C": "AGI", "D": "ASI"}, "A", "特定任務且不能遷移，符合弱 AI。強 AI 與 AGI 都指向跨任務的理論能力；ASI 更進一步指全面超越人類，因此 B、C、D 都不符。", [ref(core, "1.1 AI 的能力範疇分類", "paragraphs 30–38; table 0"), ref(exam, "L11101 Weak AI", "paragraphs 2097–2100")], "easy")
    add(2, "哪一種名稱描述的是在各領域智能表現都超越人類的假設性 AI？", {"A": "Narrow AI", "B": "Machine Learning", "C": "AGI", "D": "ASI"}, "D", "ASI 的定義關鍵是『在所有領域超越人類』。Narrow AI 只做特定任務；Machine Learning 是方法類別；AGI 著重類人通用任務能力，不等同全面超越人類。", [ref(core, "1.1 AI 的能力範疇分類", "table 0"), ref(exam, "L11101 ASI", "paragraphs 2112–2115")], "easy")
    add(3, "農場用模型分析果實影像中的顏色與大小來判斷成熟度，核心應用領域為何？", {"A": "自然語言處理", "B": "電腦視覺", "C": "語音辨識", "D": "推薦系統"}, "B", "輸入是影像且任務是辨識影像特徵，所以是電腦視覺。NLP 處理文字語言，ASR 處理語音轉文字，推薦系統依偏好排序內容，三者都不符合。", [ref(core, "1.2 AI 應用領域與產業對應", "paragraphs 40–48; table 1"), ref(exam, "L11101 Computer Vision", "paragraphs 2117–2120")], "easy")
    add(4, "客服系統要從顧客留言文字判斷情緒，最直接對應哪一領域？", {"A": "NLP", "B": "ASR", "C": "預測性維護", "D": "電腦視覺"}, "A", "理解與分析留言文字屬 NLP。ASR 是語音轉文字；預測性維護著重設備故障預警；電腦視覺處理影像，因此 B、C、D 不符。", [ref(core, "1.2 AI 應用領域與產業對應", "paragraphs 40–48; table 1"), ref(exam, "L11101 NLP", "paragraphs 2122–2125")], "easy")
    add(5, "醫療 AI 每次提出診斷建議後，都必須由醫師確認才能進入下一步。這是哪種模式？", {"A": "HITL", "B": "HOTL", "C": "HOOTL", "D": "ASI"}, "A", "每個關鍵決策都要醫師確認，符合 HITL。HOTL 是 AI 自主運作、人在上方監督；HOOTL 只在重大異常時接管；ASI 是能力層級，並非人機監督模式。", [ref(core, "1.3 AI 治理三層人機監督模式", "paragraphs 50–58; table 2"), ref(exam, "L11102 HITL", "paragraphs 2133–2136")], "easy")
    add(6, "AI 客服平常自行回覆，人員持續查看監控報表，發現異常時可立即接手。這是哪種模式？", {"A": "HITL", "B": "HOTL", "C": "HOOTL", "D": "無監督學習"}, "B", "AI 自主運作、人員日常監督且必要時介入，符合 HOTL。HITL 要求每個關鍵決策都經人審核；HOOTL 僅在重大異常才接管；無監督學習是模型學習方式。", [ref(core, "1.3 AI 治理三層人機監督模式", "paragraphs 50–58; table 2"), ref(exam, "L11102 HOTL", "paragraphs 2138–2141")], "medium")
    add(7, "某低風險自動化流程平常完全自主執行，只有發生重大故障時才由工程師接管。這是哪種模式？", {"A": "HITL", "B": "HOTL", "C": "HOOTL", "D": "XAI"}, "C", "平常完全自主、重大故障才接管，符合本教材的 HOOTL。HITL 是逐一審核，HOTL 是日常監督並可介入，XAI 則是解釋模型決策的方法。", [ref(core, "1.3 AI 治理三層人機監督模式", "paragraphs 50–58; table 2"), ref(exam, "L11102 HOOTL", "paragraphs 2143–2146")], "easy")
    add(8, "下列哪一項最符合可解釋 AI（XAI）的核心目的？", {"A": "保證模型永遠正確", "B": "讓人理解模型決策依據", "C": "完全移除資料偏差", "D": "取代所有人工審核"}, "B", "XAI 的核心是讓人理解模型的決策依據。它不保證模型永遠正確，也不能自動消除全部偏差或取代所有人工審核，因此 A、C、D 都過度肯定。", [ref(core, "1.4 可解釋 AI（XAI）四大技術", "paragraphs 60–68; table 3"), ref(exam, "L11102 XAI", "paragraphs 2153–2155")], "easy")
    add(9, "房貸模型拒絕申請後，系統指出『若年收入提高到某門檻，結果可能改為通過』。最適合的解釋方法為何？", {"A": "顯著性圖", "B": "反事實解釋", "C": "語音辨識", "D": "K-means"}, "B", "說明最小條件變動如何翻轉結果，是反事實解釋。顯著性圖標示影像關注區域；語音辨識處理語音；K-means 用於分群，因此 A、C、D 不符。", [ref(core, "1.4 可解釋 AI（XAI）四大技術", "paragraphs 60–68; table 3"), ref(exam, "L11102 Counterfactual Explanation", "paragraphs 2165–2167")], "medium")
    add(10, "關於 AI、機器學習與深度學習的範圍，下列何者最恰當？", {"A": "AI 是機器學習的子集", "B": "深度學習是機器學習的子集", "C": "機器學習與 AI 完全無關", "D": "所有 AI 都必須使用深度神經網路"}, "B", "教材直接指出深度學習是機器學習的重要子集，所以 B 正確。A 把常見包含方向顛倒；C 否定兩者關聯；D 用『所有』做過度概括，且教材未支持所有 AI 都必須使用深度神經網路。", [ref(core, "3.6 神經網路與深度學習基礎", "paragraphs 376–393"), ref("SRC-GENAI-001", "2-1 生成式 AI 的定義與本質", "paragraphs 53–55")], "medium")
    return q


def _serialized_json(payload: object) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    json.loads(serialized)
    return serialized


def write_json(path: Path, payload: object) -> None:
    """Atomically replace a JSON file after a durable temp-file write and validation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = _serialized_json(payload)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        json.loads(temporary_path.read_text(encoding="utf-8"))
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_chapter_index(path: Path, payload: object, processed_dir: Path | None = None) -> None:
    target = Path(path)
    validated = validate_chapter_index(payload, Path(processed_dir or target.parent))
    write_json(target, validated)


def process(source_dir: Path, output_dir: Path) -> None:
    missing = [name for name in EXPECTED_SOURCES if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("缺少指定教材，未產生輸出：" + "、".join(missing))

    parsed = {name: read_docx(source_dir / name) for name in EXPECTED_SOURCES}
    processed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = build_manifest(parsed, processed_at)
    failed = [item["filename"] for item in manifest if item["parse_status"] != "success"]
    if failed:
        raise RuntimeError("教材章節驗證失敗，未產生輸出：" + "、".join(failed))

    chapter_index = build_chapter_index(output_dir)
    knowledge = build_knowledge()
    questions = build_questions()
    for payload in (manifest, knowledge, questions, chapter_index):
        _serialized_json(payload)

    # Legacy L111 artifacts remain for compatibility. The formal index is
    # replaced last, so a legacy-write failure cannot damage or regress it.
    write_json(output_dir / "source_manifest.json", manifest)
    write_json(output_dir / "l111_knowledge.json", knowledge)
    write_json(output_dir / "l111_questions.json", questions)
    write_chapter_index(output_dir / "chapter_index.json", chapter_index, output_dir)
    print(f"processed {len(parsed)} sources; 10 knowledge points; 10 questions -> {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse local iPAS DOCX materials and build the L111 MVP data.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    process(args.source_dir, args.output_dir)


if __name__ == "__main__":
    main()
