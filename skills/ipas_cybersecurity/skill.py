from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "knowledge" / "processed"
SOURCE = ROOT / "knowledge" / "source"
CARDS = ROOT / "cards"
SOURCE_FILE = "iPAS_資訊安全管理概論_PART_I.pdf"
DEFAULT_CHAPTER = "I11-CIA"


class DataUnavailableError(RuntimeError):
    """A local cybersecurity slice is absent or unreadable."""


class ContentFormatError(DataUnavailableError):
    """A cybersecurity artifact breaks its content contract."""


class IpasCybersecuritySkill:
    skill_id = "ipas_cybersecurity"

    def __init__(self, processed_dir: Path | None = None, cards_dir: Path | None = None, source_dir: Path | None = None):
        self.processed_dir = Path(processed_dir or PROCESSED)
        self.cards_dir = Path(cards_dir or CARDS)
        self.source_dir = Path(source_dir or SOURCE)
        self._data: dict[str, Any] | None = None

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DataUnavailableError(f"資安教材無法讀取：{path.name}") from exc

    @staticmethod
    def _simple_filename(name: Any) -> bool:
        return isinstance(name, str) and Path(name).name == name and name not in {"", ".", ".."}

    def _load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        chapters = self._read_json(self.processed_dir / "chapter_index.json")
        sources = self._read_json(self.processed_dir / "source_manifest.json")
        if not isinstance(chapters, list) or not chapters or not isinstance(sources, list) or len(sources) != 1:
            raise ContentFormatError("章節索引或來源清單無效")
        source = sources[0]
        if source.get("filename") != SOURCE_FILE or not (self.source_dir / SOURCE_FILE).is_file():
            raise DataUnavailableError("原始 PDF 不存在或來源清單無效")
        if hashlib.sha256((self.source_dir / SOURCE_FILE).read_bytes()).hexdigest() != source.get("sha256"):
            raise ContentFormatError("原始 PDF 已變更，來源指向需要重新審核")

        topics: dict[str, dict[str, Any]] = {}
        all_chunks: dict[str, dict[str, Any]] = {}
        chapter_by_chunk: dict[str, str] = {}
        all_cards: list[dict[str, Any]] = []
        all_questions: list[dict[str, Any]] = []
        for order, index in enumerate(chapters, 1):
            if not isinstance(index, dict) or index.get("order") != order or index.get("chapter_id") in topics:
                raise ContentFormatError("章節索引順序或 ID 無效")
            if index.get("source_file") != SOURCE_FILE or not index.get("source_pages"):
                raise ContentFormatError("章節來源無效")
            if not set(index["source_pages"]) <= set(source.get("source_pages_used", [])):
                raise ContentFormatError("章節頁碼不在來源清單內")
            names = [index.get(field) for field in ("schema_file", "chunk_file", "teaching_file", "question_file")]
            if not all(self._simple_filename(name) for name in names):
                raise ContentFormatError("章節資料路徑無效")
            card_path = index.get("card_file")
            if not isinstance(card_path, str) or not card_path.startswith("cards/") or not self._simple_filename(card_path.removeprefix("cards/")):
                raise ContentFormatError("卡片路徑無效")
            schema = self._read_json(self.processed_dir / index["schema_file"])
            chunks = self._read_json(self.processed_dir / index["chunk_file"])
            questions = self._read_json(self.processed_dir / index["question_file"])
            cards = self._read_json(self.cards_dir / card_path.removeprefix("cards/"))
            try:
                teaching = (self.processed_dir / index["teaching_file"]).read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError) as exc:
                raise DataUnavailableError("教學內容無法讀取") from exc
            if schema.get("schema_version") not in {"0.1", "0.2", "0.3"} or not teaching:
                raise ContentFormatError("Learning Chunk schema 或教學內容無效")
            if not isinstance(chunks, list) or not chunks or not isinstance(cards, list) or not isinstance(questions, list):
                raise ContentFormatError("Learning Chunk、卡片或題目清單無效")
            for chunk in chunks:
                self._validate_chunk(chunk, schema, index)
                if chunk["chunk_id"] in all_chunks:
                    raise ContentFormatError("Learning Chunk ID 重複")
                all_chunks[chunk["chunk_id"]] = chunk
                chapter_by_chunk[chunk["chunk_id"]] = index["chapter_id"]
            topics[index["chapter_id"]] = {"index": index, "schema": schema, "chunks": chunks, "cards": cards, "questions": questions, "teaching": teaching}
            all_cards.extend(cards)
            all_questions.extend(questions)

        for chunk in all_chunks.values():
            if not set(chunk["teaching_interpretation"]["related_concepts"]) <= all_chunks.keys():
                raise ContentFormatError("Learning Chunk 關聯 ID 不存在")
            for relation in chunk.get("relationships", []):
                if relation["target_chunk_id"] not in all_chunks or relation["target_chunk_id"] == chunk["chunk_id"]:
                    raise ContentFormatError("Learning Chunk 關係目標無效")
                if relation["predicate"] == "precedes" and chapter_by_chunk[relation["target_chunk_id"]] != chapter_by_chunk[chunk["chunk_id"]]:
                    raise ContentFormatError("precedes 不可跨切片")
        for topic in topics.values():
            self._validate_sequence(topic["chunks"])
        for collection, key in ((all_cards, "card_id"), (all_questions, "question_id")):
            if len({item[key] for item in collection}) != len(collection):
                raise ContentFormatError("卡片或題目 ID 重複")
            if any(not item["chunk_ids"] or not set(item["chunk_ids"]) <= all_chunks.keys() for item in collection):
                raise ContentFormatError("卡片或題目引用不存在的 chunk")
        for card in all_cards:
            if not card.get("front") or not card.get("back") or card.get("content_origin") != "generated_teaching":
                raise ContentFormatError("卡片缺少正反面或內容來源")
        for question in all_questions:
            if (
                not question.get("question") or not question.get("explanation")
                or question.get("cognitive_level") not in {"recall", "distinction", "scenario"}
                or question.get("review_status") != "pending_review"
                or list(question["options"]) != list("ABCD")
                or question["correct_answer"] not in question["options"]
            ):
                raise ContentFormatError("題目選項、答案或審核狀態無效")
        self._data = {"topics": topics, "chunks": all_chunks, "sources": sources, "cards": all_cards, "questions": all_questions}
        return self._data

    @staticmethod
    def _validate_chunk(chunk: dict[str, Any], schema: dict[str, Any], index: dict[str, Any]) -> None:
        if not isinstance(chunk, dict) or not set(schema["required"]) <= chunk.keys():
            raise ContentFormatError("Learning Chunk 缺少必要欄位")
        if chunk["chunk_type"] not in schema["chunk_types"]:
            raise ContentFormatError("Learning Chunk 類型無效")
        evidence = chunk["source_evidence"]
        interpretation = chunk["teaching_interpretation"]
        if not isinstance(evidence, dict) or not set(schema["source_evidence_required"]) <= evidence.keys():
            raise ContentFormatError("Learning Chunk 缺少來源證據")
        if not isinstance(interpretation, dict) or not set(schema["teaching_interpretation_required"]) <= interpretation.keys():
            raise ContentFormatError("Learning Chunk 缺少教學解釋")
        if evidence["source_file"] != index["source_file"] or not evidence["source_pages"] or not set(evidence["source_pages"]) <= set(index["source_pages"]):
            raise ContentFormatError("Learning Chunk 來源超出章節切片")
        if not evidence["source_title"] or not evidence["observations"]:
            raise ContentFormatError("Learning Chunk 來源標題或觀察為空")
        if schema["schema_version"] == "0.1" and "relationships" in chunk:
            raise ContentFormatError("v0.1 Chunk 不支援 typed relationships")
        relations = chunk.get("relationships", [])
        if not isinstance(relations, list):
            raise ContentFormatError("Learning Chunk relationships 必須是清單")
        for relation in relations:
            if not isinstance(relation, dict) or not set(schema["relationship_required"]) <= relation.keys() or relation["predicate"] not in schema["relationship_predicates"]:
                raise ContentFormatError("Learning Chunk relationship 格式無效")

    @staticmethod
    def _validate_sequence(chunks: list[dict[str, Any]]) -> None:
        """Check one linear within-pass order; this is not a workflow engine."""
        steps = {chunk["chunk_id"] for chunk in chunks if chunk["chunk_type"] == "process"}
        edges = [
            (chunk["chunk_id"], relation["target_chunk_id"])
            for chunk in chunks for relation in chunk.get("relationships", [])
            if relation["predicate"] == "precedes"
        ]
        if not edges:
            return
        if any(source not in steps or target not in steps for source, target in edges):
            raise ContentFormatError("precedes 必須連接同一切片的 process chunks")
        positions = {chunk["chunk_id"]: number for number, chunk in enumerate(chunks)}
        if any(positions[source] >= positions[target] for source, target in edges):
            raise ContentFormatError("process 順序方向與切片記錄不一致")
        if len(edges) != len(steps) - 1:
            raise ContentFormatError("process 順序缺步驟或有循環")
        following: dict[str, str] = {}
        incoming: dict[str, int] = {step: 0 for step in steps}
        for source, target in edges:
            if source in following or incoming[target] != 0:
                raise ContentFormatError("process 順序分岔或重複")
            following[source] = target
            incoming[target] += 1
        starts = [step for step, count in incoming.items() if count == 0]
        if len(starts) != 1:
            raise ContentFormatError("process 順序有循環或起點不唯一")
        visited: set[str] = set()
        current = starts[0]
        while current not in visited:
            visited.add(current)
            if current not in following:
                break
            current = following[current]
        if len(visited) != len(steps):
            raise ContentFormatError("process 順序有循環或未連通")

    def get_course_info(self) -> dict[str, Any]:
        data = self._load()
        return {"skill_id": self.skill_id, "title": "iPAS 資訊安全工程師初級", "chapter_count": len(data["topics"]), "chunk_count": len(data["chunks"]), "card_count": len(data["cards"]), "question_count": len(data["questions"]), "first_chapter_id": DEFAULT_CHAPTER}

    def get_chapters(self) -> list[dict[str, Any]]:
        return [dict(topic["index"]) for topic in self._load()["topics"].values()]

    def get_chapter(self, chapter: str = DEFAULT_CHAPTER) -> dict[str, Any]:
        topic = self._load()["topics"].get(str(chapter).upper())
        if topic is None:
            raise ValueError(f"找不到資安切片：{chapter}")
        return {**topic["index"], "markdown": topic["teaching"], "chunks": topic["chunks"]}

    def get_flashcards(self, chapter: str = DEFAULT_CHAPTER) -> list[dict[str, Any]]:
        topic = self._load()["topics"].get(str(chapter).upper())
        if topic is None:
            raise ValueError(f"找不到資安切片：{chapter}")
        return [dict(item) for item in topic["cards"]]

    def get_questions(self, chapter: str = DEFAULT_CHAPTER) -> list[dict[str, Any]]:
        topic = self._load()["topics"].get(str(chapter).upper())
        if topic is None:
            raise ValueError(f"找不到資安切片：{chapter}")
        return [{key: value for key, value in item.items() if key not in {"correct_answer", "explanation"}} for item in topic["questions"]]

    def submit_answer(self, question_id: str, selected_answer: str) -> dict[str, Any]:
        answer = (selected_answer or "").strip().upper()
        if answer not in "ABCD" or len(answer) != 1:
            raise ValueError("答案必須是 A、B、C 或 D")
        question = next((item for item in self._load()["questions"] if item["question_id"] == (question_id or "").strip().upper()), None)
        if question is None:
            raise ValueError("找不到指定題目")
        evidence_by_id = self._load()["chunks"]
        source_references = [
            {
                "chunk_id": chunk_id,
                "source_file": evidence_by_id[chunk_id]["source_evidence"]["source_file"],
                "source_pages": evidence_by_id[chunk_id]["source_evidence"]["source_pages"],
                "source_title": evidence_by_id[chunk_id]["source_evidence"]["source_title"],
            }
            for chunk_id in question["chunk_ids"]
        ]
        return {"question_id": question["question_id"], "selected_answer": answer, "correct": answer == question["correct_answer"], "correct_answer": question["correct_answer"], "explanation": question["explanation"], "chunk_ids": question["chunk_ids"], "source_references": source_references}

    def get_sources(self) -> dict[str, Any]:
        chapters = self.get_chapters()
        return {"sources": list(self._load()["sources"]), "chapter": chapters[0], "chapters": chapters}

    def query_concept(self, query: str) -> dict[str, Any] | None:
        token = (query or "").casefold()
        if not token:
            return None
        aliases = (
            (("機密", "confidentiality"), "I11-CIA-002"),
            (("完整", "integrity"), "I11-CIA-003"),
            (("可用", "availability"), "I11-CIA-004"),
            (("脆弱", "vulnerability", "漏洞"), "I11-RISK-003"),
            (("威脅", "threat"), "I11-RISK-002"),
            (("衝擊", "impact", "可能性", "likelihood"), "I11-RISK-004"),
            (("風險評鑑", "風險識別", "風險分析", "risk assessment"), "I11-ASSESS-001"),
            (("風險", "risk"), "I11-RISK-005"),
            (("資產", "asset"), "I11-RISK-001"),
            (("cia", "三目標", "資訊安全工程師"), "I11-CIA-001"),
        )
        for terms, chunk_id in aliases:
            if any(term in token for term in terms):
                return dict(self._load()["chunks"][chunk_id])
        return None

    def answer(self, question: str) -> str:
        text = (question or "").strip()
        if not text:
            return "目前支援 CIA 三目標，以及威脅、脆弱性與風險。"
        try:
            match = re.search(r"(I11-(?:CIA|RISK)-Q\d{3}).*?(?:答案|選|答)\s*[:：]?\s*([A-D])", text, re.I)
            if match:
                result = self.submit_answer(match.group(1), match.group(2))
                refs = result["source_references"]
                pages = sorted({page for ref in refs for page in ref["source_pages"]})
                return f"{'答對' if result['correct'] else '答錯'}；正確答案 {result['correct_answer']}。{result['explanation']} 來源：{SOURCE_FILE} PDF 第 {', '.join(map(str, pages))} 頁。"
            if any(term in text for term in ("測驗", "出題", "練習題")):
                chapter = (
                    "I11-ASSESS" if any(term in text.casefold() for term in ("評鑑", "識別", "分析", "assessment"))
                    else "I11-RISK" if any(term in text.casefold() for term in ("風險", "risk", "威脅", "脆弱"))
                    else DEFAULT_CHAPTER
                )
                item = self.get_questions(chapter)[0]
                return f"{item['question_id']} {item['question']}\n" + "\n".join(f"{key}. {value}" for key, value in item["options"].items())
            chunk = self.query_concept(text)
            if chunk is None:
                return "目前只支援 CIA 三目標，以及威脅、脆弱性與風險。"
            teaching = chunk["teaching_interpretation"]
            evidence = chunk["source_evidence"]
            return f"{chunk['title']}：{teaching['core_concept']}\n{teaching['explanation']}\n考點：{teaching['exam_focus']}\n來源：{evidence['source_file']} PDF 第 {', '.join(map(str, evidence['source_pages']))} 頁。"
        except (DataUnavailableError, ValueError) as exc:
            return str(exc)


_default_skill = IpasCybersecuritySkill()


def configure(_ask_gpt_func: Callable[[str, str], str]) -> None:
    pass


def answer(question: str) -> str:
    return _default_skill.answer(question)


def get_course_info() -> dict[str, Any]:
    return _default_skill.get_course_info()


def get_chapters() -> list[dict[str, Any]]:
    return _default_skill.get_chapters()


def get_chapter(chapter: str = DEFAULT_CHAPTER) -> dict[str, Any]:
    return _default_skill.get_chapter(chapter)


def get_flashcards(chapter: str = DEFAULT_CHAPTER) -> list[dict[str, Any]]:
    return _default_skill.get_flashcards(chapter)


def get_questions(chapter: str = DEFAULT_CHAPTER) -> list[dict[str, Any]]:
    return _default_skill.get_questions(chapter)


def submit_answer(question_id: str, selected_answer: str) -> dict[str, Any]:
    return _default_skill.submit_answer(question_id, selected_answer)


def get_sources() -> dict[str, Any]:
    return _default_skill.get_sources()


def query_concept(query: str) -> dict[str, Any] | None:
    return _default_skill.query_concept(query)
