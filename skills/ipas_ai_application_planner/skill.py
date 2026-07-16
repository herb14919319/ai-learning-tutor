from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Callable


SKILL_ID = "ipas_ai_application_planner"
ROOT = Path(__file__).resolve().parent
DEFAULT_PROCESSED_DIR = ROOT / "knowledge" / "processed"
LEGACY_DATA_FILES = (
    "source_manifest.json",
    "l111_knowledge.json",
    "l111_questions.json",
)
CHAPTER_INDEX_FILE = "chapter_index.json"
CHAPTER_COUNT = 7
QUESTIONS_PER_CHAPTER = 8
TOTAL_QUESTION_COUNT = CHAPTER_COUNT * QUESTIONS_PER_CHAPTER
INDEX_REQUIRED_FIELDS = {
    "chapter_id",
    "lesson_code",
    "title",
    "order",
    "source_file",
    "status",
}
PUBLIC_QUESTION_FIELDS = (
    "question_id",
    "chapter_id",
    "question_number",
    "question_text",
    "options",
)


class DataUnavailableError(RuntimeError):
    """Raised when required local teaching material has not been processed."""


class ContentFormatError(DataUnavailableError):
    """Raised when processed course material does not match the required contract."""


class IpasAiApplicationPlannerSkill:
    skill_id = SKILL_ID

    def __init__(self, processed_dir: Path | None = None, *, rng: random.Random | None = None):
        self.processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)
        self.rng = rng or random.Random()
        self._legacy_data: dict[str, Any] | None = None
        self._course_data: dict[str, Any] | None = None

    def _load_legacy(self) -> dict[str, Any]:
        if self._legacy_data is not None:
            return self._legacy_data

        missing = [name for name in LEGACY_DATA_FILES if not (self.processed_dir / name).is_file()]
        if missing:
            raise DataUnavailableError(
                "iPAS 教材尚未完成解析；缺少：" + "、".join(missing)
            )

        try:
            self._legacy_data = {
                "manifest": self._read_json("source_manifest.json"),
                "knowledge": self._read_json("l111_knowledge.json"),
                "questions": self._read_json("l111_questions.json"),
            }
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise DataUnavailableError(f"iPAS 教材資料無法讀取：{exc}") from exc

        if not self._legacy_data["knowledge"] or not self._legacy_data["questions"]:
            raise DataUnavailableError("iPAS L111 教材或題庫為空，請重新解析教材。")
        return self._legacy_data

    def _read_json(self, filename: str) -> Any:
        return json.loads((self.processed_dir / filename).read_text(encoding="utf-8"))

    @staticmethod
    def _format_error(
        chapter_id: str,
        source_file: str,
        detail: str,
        *,
        question_number: int | None = None,
    ) -> ContentFormatError:
        question = f"，題號 {question_number}" if question_number is not None else ""
        return ContentFormatError(
            f"iPAS 正式教材格式錯誤：章節 {chapter_id}（{source_file}）{question}：{detail}"
        )

    @staticmethod
    def _normalize_title(title: str) -> str:
        return re.sub(r"^第\s*[一二三四五六七1-7]\s*章\s*[：:]?\s*", "", title).strip()

    def _read_chapter_index(self) -> list[dict[str, Any]]:
        path = self.processed_dir / CHAPTER_INDEX_FILE
        if not path.is_file():
            raise DataUnavailableError(f"iPAS 正式教材缺少章節索引：{CHAPTER_INDEX_FILE}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataUnavailableError(f"iPAS 正式教材章節索引無法讀取：{exc}") from exc
        if not isinstance(payload, list):
            raise ContentFormatError("iPAS 正式教材章節索引必須是 JSON 陣列。")
        if len(payload) != CHAPTER_COUNT:
            raise ContentFormatError(
                f"iPAS 正式教材章節索引應有 {CHAPTER_COUNT} 章，實際為 {len(payload)} 章。"
            )

        entries: list[dict[str, Any]] = []
        for position, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise ContentFormatError(f"iPAS 正式教材章節索引第 {position} 筆必須是物件。")
            missing = sorted(INDEX_REQUIRED_FIELDS - item.keys())
            chapter_id = str(item.get("chapter_id") or f"index-{position}")
            source_file = str(item.get("source_file") or "未指定檔案")
            if missing:
                raise self._format_error(
                    chapter_id,
                    source_file,
                    "chapter_index 缺少欄位：" + "、".join(missing),
                )
            if not isinstance(item["order"], int):
                raise self._format_error(chapter_id, source_file, "order 必須是整數")
            if Path(source_file).name != source_file or Path(source_file).suffix.casefold() != ".md":
                raise self._format_error(chapter_id, source_file, "source_file 必須是同目錄下的 Markdown 檔名")
            if item["status"] != "completed":
                raise self._format_error(chapter_id, source_file, "status 必須為 completed")
            entries.append(dict(item))

        entries.sort(key=lambda item: item["order"])
        expected_orders = list(range(1, CHAPTER_COUNT + 1))
        actual_orders = [item["order"] for item in entries]
        if actual_orders != expected_orders:
            raise ContentFormatError(
                f"iPAS 正式教材章節 order 必須為 {expected_orders}，實際為 {actual_orders}。"
            )
        for field in ("chapter_id", "lesson_code", "source_file"):
            values = [str(item[field]).casefold() for item in entries]
            if len(values) != len(set(values)):
                raise ContentFormatError(f"iPAS 正式教材章節索引的 {field} 不可重複。")
        return entries

    def _parse_questions(
        self,
        *,
        chapter_id: str,
        lesson_code: str,
        source_file: str,
        quiz_markdown: str,
        answer_markdown: str,
    ) -> list[dict[str, Any]]:
        question_pattern = re.compile(r"^\s*\*\*(\d+)[.、)]\s*(.+?)\*\*\s*$")
        option_pattern = re.compile(r"^\s*([A-D])[.、)]\s*(.+?)\s*$")
        answer_pattern = re.compile(r"^\s*(\d+)[.、)]\s*\*\*([A-D])\*\*[。．.]?\s*(.*)$")

        raw_questions: dict[int, dict[str, Any]] = {}
        current_number: int | None = None
        for line_number, line in enumerate(quiz_markdown.splitlines(), start=1):
            if not line.strip():
                continue
            question_match = question_pattern.match(line)
            if question_match:
                number = int(question_match.group(1))
                if number in raw_questions:
                    raise self._format_error(
                        chapter_id, source_file, "題號重複", question_number=number
                    )
                raw_questions[number] = {
                    "question_text": question_match.group(2).strip(),
                    "options": {},
                }
                current_number = number
                continue
            option_match = option_pattern.match(line)
            if option_match and current_number is not None:
                letter, option_text = option_match.groups()
                options = raw_questions[current_number]["options"]
                if letter in options:
                    raise self._format_error(
                        chapter_id,
                        source_file,
                        f"選項 {letter} 重複",
                        question_number=current_number,
                    )
                options[letter] = option_text.strip()
                continue
            raise self._format_error(
                chapter_id,
                source_file,
                f"自我測驗第 {line_number} 行無法辨識：{line.strip()[:80]}",
                question_number=current_number,
            )

        answers: dict[int, dict[str, str]] = {}
        current_answer: int | None = None
        for line_number, line in enumerate(answer_markdown.splitlines(), start=1):
            if not line.strip():
                continue
            answer_match = answer_pattern.match(line)
            if answer_match:
                number = int(answer_match.group(1))
                if number in answers:
                    raise self._format_error(
                        chapter_id, source_file, "答案題號重複", question_number=number
                    )
                answers[number] = {
                    "correct_answer": answer_match.group(2),
                    "explanation": answer_match.group(3).strip(),
                }
                current_answer = number
                continue
            if current_answer is None:
                raise self._format_error(
                    chapter_id,
                    source_file,
                    f"答案與解析第 {line_number} 行無法辨識：{line.strip()[:80]}",
                )
            answers[current_answer]["explanation"] = (
                answers[current_answer]["explanation"] + " " + line.strip()
            ).strip()

        expected_numbers = list(range(1, QUESTIONS_PER_CHAPTER + 1))
        if sorted(raw_questions) != expected_numbers:
            raise self._format_error(
                chapter_id,
                source_file,
                f"題號必須完整且連續為 {expected_numbers}，實際為 {sorted(raw_questions)}",
            )
        if sorted(answers) != expected_numbers:
            raise self._format_error(
                chapter_id,
                source_file,
                f"答案題號必須完整且連續為 {expected_numbers}，實際為 {sorted(answers)}",
            )

        questions: list[dict[str, Any]] = []
        for number in expected_numbers:
            item = raw_questions[number]
            options = item["options"]
            if list(options) != list("ABCD"):
                missing = [letter for letter in "ABCD" if letter not in options]
                detail = "選項必須依序包含 A、B、C、D"
                if missing:
                    detail += "；缺少：" + "、".join(missing)
                raise self._format_error(
                    chapter_id, source_file, detail, question_number=number
                )
            answer = answers[number]
            if not item["question_text"]:
                raise self._format_error(
                    chapter_id, source_file, "缺少題目文字", question_number=number
                )
            if not answer["explanation"]:
                raise self._format_error(
                    chapter_id, source_file, "缺少解題解析", question_number=number
                )
            if answer["correct_answer"] not in options:
                raise self._format_error(
                    chapter_id, source_file, "正確答案沒有對應選項", question_number=number
                )
            questions.append(
                {
                    "question_id": f"{lesson_code.upper()}-Q{number:03d}",
                    "chapter_id": chapter_id,
                    "question_number": number,
                    "question_text": item["question_text"],
                    "options": dict(options),
                    "correct_answer": answer["correct_answer"],
                    "explanation": answer["explanation"],
                }
            )
        return questions

    def _parse_chapter(self, index_item: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        chapter_id = str(index_item["chapter_id"])
        lesson_code = str(index_item["lesson_code"])
        source_file = str(index_item["source_file"])
        path = self.processed_dir / source_file
        if not path.is_file():
            raise DataUnavailableError(
                f"iPAS 正式教材缺少章節 {chapter_id} 的 Markdown：{source_file}"
            )
        try:
            markdown = path.read_text(encoding="utf-8-sig").strip()
        except OSError as exc:
            raise DataUnavailableError(
                f"iPAS 正式教材無法讀取章節 {chapter_id}：{source_file}"
            ) from exc
        if not markdown:
            raise self._format_error(chapter_id, source_file, "Markdown 內容為空")

        title_match = re.search(r"^#\s+(.+?)\s*$", markdown, flags=re.M)
        if not title_match:
            raise self._format_error(chapter_id, source_file, "缺少一級章節標題")
        markdown_title = self._normalize_title(title_match.group(1))
        if markdown_title != self._normalize_title(str(index_item["title"])):
            raise self._format_error(
                chapter_id,
                source_file,
                f"Markdown 標題「{markdown_title}」與 chapter_index 標題「{index_item['title']}」不一致",
            )

        quiz_matches = list(re.finditer(r"^#{2,6}\s+自我測驗\s*$", markdown, flags=re.M))
        answer_matches = list(re.finditer(r"^#{2,6}\s+答案與解析\s*$", markdown, flags=re.M))
        if len(quiz_matches) != 1:
            raise self._format_error(
                chapter_id, source_file, f"自我測驗區段應恰好一個，實際為 {len(quiz_matches)} 個"
            )
        if len(answer_matches) != 1:
            raise self._format_error(
                chapter_id, source_file, f"答案與解析區段應恰好一個，實際為 {len(answer_matches)} 個"
            )
        quiz_match = quiz_matches[0]
        answer_match = answer_matches[0]
        if answer_match.start() <= quiz_match.end():
            raise self._format_error(chapter_id, source_file, "答案與解析必須位於自我測驗之後")

        content_markdown = markdown[: quiz_match.start()].rstrip()
        quiz_markdown = markdown[quiz_match.end() : answer_match.start()].strip()
        answer_markdown = markdown[answer_match.end() :].strip()
        if not content_markdown:
            raise self._format_error(chapter_id, source_file, "缺少章節正文")
        questions = self._parse_questions(
            chapter_id=chapter_id,
            lesson_code=lesson_code,
            source_file=source_file,
            quiz_markdown=quiz_markdown,
            answer_markdown=answer_markdown,
        )
        chapter = {
            "chapter_id": chapter_id,
            "lesson_code": lesson_code,
            "title": str(index_item["title"]),
            "source_file": source_file,
            "order": index_item["order"],
            "content_markdown": content_markdown,
            "question_count": len(questions),
        }
        return chapter, questions

    def _load_course(self) -> dict[str, Any]:
        if self._course_data is not None:
            return self._course_data
        if not self.processed_dir.is_dir():
            raise DataUnavailableError(f"iPAS 正式教材目錄不存在：{self.processed_dir}")

        chapters: list[dict[str, Any]] = []
        questions: list[dict[str, Any]] = []
        for item in self._read_chapter_index():
            chapter, chapter_questions = self._parse_chapter(item)
            chapters.append(chapter)
            questions.extend(chapter_questions)
        if len(questions) != TOTAL_QUESTION_COUNT:
            raise ContentFormatError(
                f"iPAS 正式教材題庫應有 {TOTAL_QUESTION_COUNT} 題，實際為 {len(questions)} 題。"
            )
        question_ids = [item["question_id"] for item in questions]
        if len(question_ids) != len(set(question_ids)):
            raise ContentFormatError("iPAS 正式教材題號不可重複。")
        self._course_data = {"chapters": chapters, "questions": questions}
        return self._course_data

    @staticmethod
    def _public_question(question: dict[str, Any]) -> dict[str, Any]:
        return {
            key: dict(question[key]) if key == "options" else question[key]
            for key in PUBLIC_QUESTION_FIELDS
        }

    def get_course_info(self) -> dict[str, Any]:
        data = self._load_course()
        return {
            "skill_id": self.skill_id,
            "title": "iPAS AI 應用規劃師正式課程",
            "chapter_count": len(data["chapters"]),
            "question_count": len(data["questions"]),
            "first_chapter_id": data["chapters"][0]["chapter_id"],
        }

    def get_chapters(self) -> list[dict[str, Any]]:
        return [dict(chapter) for chapter in self._load_course()["chapters"]]

    def _find_chapter(self, chapter: int | str) -> dict[str, Any]:
        chapters = self._load_course()["chapters"]
        if isinstance(chapter, int):
            match = next((item for item in chapters if item["order"] == chapter), None)
        else:
            token = str(chapter or "").strip().casefold()
            match = next(
                (
                    item
                    for item in chapters
                    if token
                    in {
                        item["chapter_id"].casefold(),
                        item["lesson_code"].casefold(),
                        str(item["order"]),
                    }
                ),
                None,
            )
        if match is None:
            raise ValueError(f"找不到 iPAS 正式教材章節：{chapter}")
        return match

    def get_chapter(self, chapter: int | str) -> dict[str, Any]:
        return dict(self._find_chapter(chapter))

    def get_questions(self, chapter: int | str | None = None) -> list[dict[str, Any]]:
        questions = self._load_course()["questions"]
        if chapter is not None:
            chapter_id = self._find_chapter(chapter)["chapter_id"]
            questions = [item for item in questions if item["chapter_id"] == chapter_id]
        return [self._public_question(item) for item in questions]

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
        for item in self._load_legacy()["knowledge"]:
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
            for item in self._load_legacy()["knowledge"]
        ]

    def get_random_question(self) -> dict[str, Any]:
        question = self.rng.choice(self._load_course()["questions"])
        return self._public_question(question)

    def _find_question(self, question_id: str) -> dict[str, Any]:
        normalized = (question_id or "").strip().upper()
        question = next(
            (
                item
                for item in self._load_course()["questions"]
                if item["question_id"].upper() == normalized
            ),
            None,
        )
        if question is None:
            raise ValueError(f"找不到題目：{normalized or question_id}")
        return question

    def submit_answer(self, question_id: str, selected_answer: str) -> dict[str, Any]:
        selected = (selected_answer or "").strip().upper().strip("()（）")
        if selected not in "ABCD" or len(selected) != 1:
            raise ValueError("答案必須是 A、B、C 或 D。")
        question = self._find_question(question_id)
        correct_answer = question["correct_answer"]
        return {
            "question_id": question["question_id"],
            "chapter_id": question["chapter_id"],
            "selected_answer": selected,
            "correct": selected == correct_answer,
            "correct_answer": correct_answer,
            "explanation": question["explanation"],
        }

    def get_sources(self) -> dict[str, Any]:
        legacy = self._load_legacy()
        l111 = next((item for item in self.get_chapters() if item["lesson_code"] == "L111"), None)
        return {"sources": legacy["manifest"], "chapter": l111}

    def answer(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "請輸入想查詢的 L111 觀念，例如：弱 AI、HITL、XAI。"
        try:
            question_source_match = re.search(r"(L1(?:1[1-4]|2[1-3])-Q\d{3}).*?(?:來源|出處)", question, re.I)
            if question_source_match:
                return self._format_question_sources(question_source_match.group(1))
            answer_match = re.search(r"(L1(?:1[1-4]|2[1-3])-Q\d{3}).*?(?:答案|選|答)\s*[:：]?\s*\(?([A-D])\)?", question, re.I)
            if not answer_match:
                answer_match = re.search(r"(L1(?:1[1-4]|2[1-3])-Q\d{3})\s+\(?([A-D])\)?", question, re.I)
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
            f"{item['question_id']}\n{item['question_text']}\n{options}\n\n"
            f"請用「{item['question_id']} 答案 [A-D]」的格式作答。\n"
            f"查詢本題來源請輸入「{item['question_id']} 來源」。\n"
            "本題來自正式課程章末自我測驗。"
        )

    def _format_question_sources(self, question_id: str) -> str:
        try:
            question = self._find_question(question_id)
        except ValueError as exc:
            return str(exc)
        chapter = self._find_chapter(question["chapter_id"])
        return (
            f"{question['question_id']} 來源：{chapter['title']}"
            f"（{chapter['lesson_code']}，{chapter['source_file']}）"
        )

    def _format_supervision_comparison(self) -> str:
        ids = ("L111-K006", "L111-K007", "L111-K008")
        items = [
            next(item for item in self._load_legacy()["knowledge"] if item["knowledge_id"] == knowledge_id)
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
            f"解析：{result['explanation']}"
        )

    def _format_sources(self, payload: dict[str, Any]) -> str:
        lines = ["L111 教材與章節來源"]
        for source in payload["sources"]:
            lines.append(
                f"- {source['source_id']}｜{source['title']}｜{source['filename']}｜{source['source_role']}"
            )
        chapter = payload["chapter"]
        lines.append(f"\n章節：{chapter['title']}（{chapter['lesson_code']}）")
        lines.append(f"- {chapter['source_file']}")
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


def get_questions(chapter: int | str | None = None) -> list[dict[str, Any]]:
    return _default_skill.get_questions(chapter)


def submit_answer(question_id: str, selected_answer: str) -> dict[str, Any]:
    return _default_skill.submit_answer(question_id, selected_answer)


def get_sources() -> dict[str, Any]:
    return _default_skill.get_sources()


def get_course_info() -> dict[str, Any]:
    return _default_skill.get_course_info()


def get_chapters() -> list[dict[str, Any]]:
    return _default_skill.get_chapters()


def get_chapter(chapter: int | str) -> dict[str, Any]:
    return _default_skill.get_chapter(chapter)
