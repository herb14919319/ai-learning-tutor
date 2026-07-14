from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Callable


SKILL_ID = "ipas_ai_application_planner"
ROOT = Path(__file__).resolve().parent
DEFAULT_PROCESSED_DIR = ROOT / "knowledge" / "processed"
REQUIRED_DATA_FILES = (
    "source_manifest.json",
    "chapter_index.json",
    "l111_knowledge.json",
    "l111_questions.json",
)


class DataUnavailableError(RuntimeError):
    """Raised when required local teaching material has not been processed."""


class IpasAiApplicationPlannerSkill:
    skill_id = SKILL_ID

    def __init__(self, processed_dir: Path | None = None, *, rng: random.Random | None = None):
        self.processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)
        self.rng = rng or random.Random()
        self._data: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data

        missing = [name for name in REQUIRED_DATA_FILES if not (self.processed_dir / name).is_file()]
        if missing:
            raise DataUnavailableError(
                "iPAS 教材尚未完成解析；缺少：" + "、".join(missing)
            )

        try:
            self._data = {
                "manifest": self._read_json("source_manifest.json"),
                "chapters": self._read_json("chapter_index.json"),
                "knowledge": self._read_json("l111_knowledge.json"),
                "questions": self._read_json("l111_questions.json"),
            }
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise DataUnavailableError(f"iPAS 教材資料無法讀取：{exc}") from exc

        if not self._data["knowledge"] or not self._data["questions"]:
            raise DataUnavailableError("iPAS L111 教材或題庫為空，請重新解析教材。")
        return self._data

    def _read_json(self, filename: str) -> Any:
        return json.loads((self.processed_dir / filename).read_text(encoding="utf-8"))

    def query_concept(self, query: str) -> dict[str, Any] | None:
        query = (query or "").strip()
        if not query:
            return None

        aliases = {
            "人工智慧": ("AI 定義", "人工智慧定義"),
            "弱ai": ("弱 AI", "Narrow AI"),
            "強ai": ("強 AI", "Strong AI"),
            "通用人工智慧": ("AGI",),
            "超級人工智慧": ("ASI",),
            "人在迴圈中": ("HITL",),
            "人在迴圈上": ("HOTL",),
            "人在迴圈外": ("HOOTL",),
            "可解釋": ("XAI",),
            "深度學習": ("機器學習", "深度學習"),
            "應用": ("應用領域",),
            "陷阱": ("常見考試陷阱",),
        }
        normalized = re.sub(r"\s+", "", query).lower()
        terms = {normalized}
        for key, values in aliases.items():
            if key.lower() in normalized or any(value.lower().replace(" ", "") in normalized for value in values):
                terms.update(value.lower().replace(" ", "") for value in values)

        best: tuple[int, dict[str, Any] | None] = (0, None)
        for item in self._load()["knowledge"]:
            haystack = " ".join(
                [item["title"], item["definition"], *item.get("key_points", []), *item.get("common_confusions", [])]
            ).lower().replace(" ", "")
            score = sum(3 if term in item["title"].lower().replace(" ", "") else 1 for term in terms if term and term in haystack)
            if score > best[0]:
                best = (score, item)
        return best[1]

    def get_key_points(self) -> list[dict[str, Any]]:
        return [
            {
                "knowledge_id": item["knowledge_id"],
                "title": item["title"],
                "key_points": item["key_points"],
                "source_references": item["source_references"],
            }
            for item in self._load()["knowledge"]
        ]

    def get_random_question(self) -> dict[str, Any]:
        question = self.rng.choice(self._load()["questions"])
        return {
            key: question[key]
            for key in (
                "question_id",
                "topic_code",
                "question",
                "options",
                "difficulty",
                "question_type",
                "source_references",
                "review_status",
            )
        }

    def submit_answer(self, question_id: str, selected_answer: str) -> dict[str, Any]:
        question_id = (question_id or "").strip().upper()
        selected = (selected_answer or "").strip().upper().strip("()（）")
        for question in self._load()["questions"]:
            if question["question_id"].upper() != question_id:
                continue
            correct_answer = question["correct_answer"].upper()
            return {
                "question_id": question["question_id"],
                "selected_answer": selected,
                "correct": selected == correct_answer,
                "correct_answer": correct_answer,
                "explanation": question["explanation"],
                "source_references": question["source_references"],
            }
        raise ValueError(f"找不到題目：{question_id}")

    def get_sources(self) -> dict[str, Any]:
        data = self._load()
        l111 = next((item for item in data["chapters"] if item["topic_code"] == "L111"), None)
        return {"sources": data["manifest"], "chapter": l111}

    def answer(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "請輸入想查詢的 L111 觀念，例如：弱 AI、HITL、XAI。"
        try:
            question_source_match = re.search(r"(L111-Q\d{3}).*?(?:來源|出處)", question, re.I)
            if question_source_match:
                return self._format_question_sources(question_source_match.group(1))
            answer_match = re.search(r"(L111-Q\d{3}).*?(?:答案|選|答)\s*[:：]?\s*\(?([A-D])\)?", question, re.I)
            if not answer_match:
                answer_match = re.search(r"(L111-Q\d{3})\s+\(?([A-D])\)?", question, re.I)
            if answer_match:
                return self._format_submission(self.submit_answer(answer_match.group(1), answer_match.group(2)))
            if re.search(r"(?:答案|選|答)\s*[:：]?\s*\(?[A-D]\)?", question, re.I):
                return "無法判定要回答哪一題。請附上題號，例如：L111-Q001 答案 B。"
            if "這題" in question and any(term in question for term in ("來源", "出處")):
                return "無法判定你指的是哪一題。請附上題號，例如：L111-Q001 來源。"
            if any(term in question for term in ("測驗", "出題", "考我", "隨機一題", "練習題")):
                return self._format_question(self.get_random_question())
            if any(term in question for term in ("重點", "整理", "總覽")):
                return self._format_key_points(self.get_key_points())
            if any(term in question for term in ("來源", "教材", "章節", "出處")):
                return self._format_sources(self.get_sources())
            if all(term.lower() in question.lower() for term in ("HITL", "HOTL", "HOOTL")):
                return self._format_supervision_comparison()

            concept = self.query_concept(question)
            if not concept:
                return "目前第一階段只支援 L111 人工智慧概念；找不到對應觀念，請換個關鍵詞。"
            return self._format_concept(concept)
        except DataUnavailableError as exc:
            return str(exc)
        except ValueError as exc:
            return str(exc)

    @staticmethod
    def _reference_lines(references: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"- {ref['source_id']}｜{ref['section']}｜{ref['locator']}" for ref in references
        )

    def _format_concept(self, item: dict[str, Any]) -> str:
        points = "\n".join(f"- {point}" for point in item["key_points"])
        confusions = "\n".join(f"- {point}" for point in item["common_confusions"])
        flags = []
        if item.get("conflict"):
            flags.append("此觀念在教材間有措辭差異，已保留來源差異，需人工審核。")
        if item.get("requires_review"):
            flags.append("此項目需人工審核。")
        flag_text = ("\n\n注意：" + " ".join(flags)) if flags else ""
        return (
            f"{item['title']}\n\n定義：{item['definition']}\n\n白話：{item['plain_explanation']}"
            f"\n\n重點：\n{points}\n\n常見混淆：\n{confusions}"
            f"\n\n來源：\n{self._reference_lines(item['source_references'])}{flag_text}"
        )

    def _format_key_points(self, items: list[dict[str, Any]]) -> str:
        lines = ["L111 人工智慧概念重點"]
        for item in items:
            lines.append(f"\n{item['title']}：{item['key_points'][0]}")
        lines.append(
            "\n主要來源：SRC-CORE-001 第 1 章 1.1–1.5；"
            "SRC-EXAM-001 第六章 L11101–L11102；"
            "SRC-GENAI-001 第 9 章治理補充。"
        )
        lines.append("所有項目皆為 pending_review；可再用觀念名稱查詢完整來源。")
        return "\n".join(lines)

    def _format_question(self, item: dict[str, Any]) -> str:
        options = "\n".join(f"({key}) {value}" for key, value in item["options"].items())
        return (
            f"{item['question_id']}｜{item['difficulty']}\n{item['question']}\n{options}\n\n"
            f"請用「{item['question_id']} 答案 [A-D]」的格式作答。\n"
            f"查詢本題來源請輸入「{item['question_id']} 來源」。\n"
            "本題為依教材觀念改寫的練習題，非官方題目。"
        )

    def _format_question_sources(self, question_id: str) -> str:
        normalized = question_id.upper()
        question = next(
            (item for item in self._load()["questions"] if item["question_id"].upper() == normalized),
            None,
        )
        if not question:
            return f"找不到題目：{normalized}"
        return f"{question['question_id']} 來源：\n{self._reference_lines(question['source_references'])}"

    def _format_supervision_comparison(self) -> str:
        ids = ("L111-K006", "L111-K007", "L111-K008")
        items = [
            next(item for item in self._load()["knowledge"] if item["knowledge_id"] == knowledge_id)
            for knowledge_id in ids
        ]
        lines = ["HITL、HOTL、HOOTL 的差別在於人類介入時機："]
        for item in items:
            lines.append(f"- {item['title']}：{item['definition']}")
        lines.append("\n來源：")
        seen = set()
        for item in items:
            for reference in item["source_references"]:
                key = (reference["source_id"], reference["section"], reference["locator"])
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- {key[0]}｜{key[1]}｜{key[2]}")
        return "\n".join(lines)

    def _format_submission(self, result: dict[str, Any]) -> str:
        verdict = "答對了" if result["correct"] else "答錯了"
        return (
            f"{verdict}。正確答案：{result['correct_answer']}\n\n"
            f"解析：{result['explanation']}\n\n來源：\n"
            f"{self._reference_lines(result['source_references'])}"
        )

    def _format_sources(self, payload: dict[str, Any]) -> str:
        lines = ["L111 教材與章節來源"]
        for source in payload["sources"]:
            lines.append(
                f"- {source['source_id']}｜{source['title']}｜{source['filename']}｜{source['source_role']}"
            )
        chapter = payload["chapter"]
        lines.append(f"\n章節：{chapter['title']}（{chapter['topic_code']}）")
        lines.extend(f"- {ref}" for ref in chapter["page_or_section_reference"])
        return "\n".join(lines)


_default_skill = IpasAiApplicationPlannerSkill()


def configure(_ask_gpt_func: Callable[[str, str], str]) -> None:
    """Tutor adapter hook; this deterministic MVP does not call an external model."""


def answer(question: str) -> str:
    return _default_skill.answer(question)


def query_concept(query: str) -> dict[str, Any] | None:
    return _default_skill.query_concept(query)


def get_key_points() -> list[dict[str, Any]]:
    return _default_skill.get_key_points()


def get_random_question() -> dict[str, Any]:
    return _default_skill.get_random_question()


def submit_answer(question_id: str, selected_answer: str) -> dict[str, Any]:
    return _default_skill.submit_answer(question_id, selected_answer)


def get_sources() -> dict[str, Any]:
    return _default_skill.get_sources()
