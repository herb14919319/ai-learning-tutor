from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path
from typing import Any, Callable


SKILL_ID = "ipas_net_zero_planner"
ROOT = Path(__file__).resolve().parent
DEFAULT_PROCESSED_DIR = ROOT / "knowledge" / "processed"
DEFAULT_CARDS_DIR = ROOT / "cards"
CHAPTER_COUNT = 8
CHAPTER_PATTERN = re.compile(r"^ch(?P<number>0[1-8])_[a-z0-9_]+\.md$", re.I)


class DataUnavailableError(RuntimeError):
    """Raised when required local teaching material is unavailable."""


class IpasNetZeroPlannerSkill:
    skill_id = SKILL_ID

    def __init__(
        self,
        processed_dir: Path | None = None,
        *,
        cards_dir: Path | None = None,
        rng: random.Random | None = None,
    ):
        self.processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)
        self.cards_dir = Path(cards_dir or DEFAULT_CARDS_DIR)
        self.rng = rng or random.Random()
        self._chapters: list[dict[str, Any]] | None = None

    @staticmethod
    def _natural_key(path: Path) -> list[int | str]:
        return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]

    @staticmethod
    def _plain_text(markdown: str) -> str:
        text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
        text = re.sub(r"!\[[^]]*]\([^)]*\)", " ", text)
        text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
        text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)
        text = re.sub(r"[*_>`~|]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _title(markdown: str, fallback: str) -> str:
        match = re.search(r"^#\s+(.+?)\s*$", markdown, flags=re.M)
        return match.group(1).strip() if match else fallback

    @staticmethod
    def _headings(markdown: str) -> list[str]:
        return [
            match.group(1).strip()
            for match in re.finditer(r"^##\s+(.+?)\s*$", markdown, flags=re.M)
            if match.group(1).strip()
        ]

    @staticmethod
    def _summary(markdown: str, title: str) -> str:
        for block in re.split(r"\n\s*\n", markdown):
            candidate = block.strip()
            if not candidate or candidate.startswith(("#", "```", "---")):
                continue
            plain = IpasNetZeroPlannerSkill._plain_text(candidate)
            if len(plain) >= 20:
                return plain[:220] + ("…" if len(plain) > 220 else "")
        return f"{title}課程內容"

    def _card_paths(self, chapter_id: str) -> list[str]:
        directory = self.cards_dir / chapter_id
        if not directory.is_dir():
            return []
        image_paths = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        ]
        return [
            path.relative_to(ROOT).as_posix()
            for path in sorted(image_paths, key=self._natural_key)
        ]

    def _load(self) -> list[dict[str, Any]]:
        if self._chapters is not None:
            return self._chapters
        if not self.processed_dir.is_dir():
            raise DataUnavailableError(f"iPAS 淨零碳規劃師教材目錄不存在：{self.processed_dir}")

        matched: dict[int, Path] = {}
        for path in self.processed_dir.glob("ch*.md"):
            match = CHAPTER_PATTERN.match(path.name)
            if match:
                matched[int(match.group("number"))] = path

        missing = [f"ch{number:02d}" for number in range(1, CHAPTER_COUNT + 1) if number not in matched]
        if missing:
            raise DataUnavailableError("iPAS 淨零碳規劃師缺少章節教材：" + "、".join(missing))

        chapters: list[dict[str, Any]] = []
        for number in range(1, CHAPTER_COUNT + 1):
            path = matched[number]
            try:
                markdown = path.read_text(encoding="utf-8-sig").strip()
            except OSError as exc:
                raise DataUnavailableError(f"無法讀取 iPAS 淨零碳規劃師教材：{path.name}") from exc
            if not markdown:
                raise DataUnavailableError(f"iPAS 淨零碳規劃師章節教材為空：{path.name}")

            chapter_id = f"ch{number:02d}"
            title = self._title(markdown, f"第{number}章")
            chapters.append(
                {
                    "chapter_id": chapter_id,
                    "chapter_number": number,
                    "title": title,
                    "summary": self._summary(markdown, title),
                    "headings": self._headings(markdown),
                    "markdown": markdown,
                    "source_file": path.name,
                    "source_path": f"knowledge/processed/{path.name}",
                    "cards": self._card_paths(chapter_id),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        self._chapters = chapters
        return chapters

    @staticmethod
    def _chapter_number(chapter: int | str) -> int:
        if isinstance(chapter, int):
            number = chapter
        else:
            match = re.search(r"(?:ch)?\s*0?([1-8])", str(chapter).strip(), flags=re.I)
            if not match:
                raise ValueError(f"無效的章節：{chapter}")
            number = int(match.group(1))
        if number not in range(1, CHAPTER_COUNT + 1):
            raise ValueError(f"章節必須介於 1 到 {CHAPTER_COUNT}")
        return number

    @staticmethod
    def _navigation(chapters: list[dict[str, Any]], index: int) -> dict[str, Any]:
        previous = chapters[index - 1] if index > 0 else None
        following = chapters[index + 1] if index + 1 < len(chapters) else None
        return {
            "previous_chapter": (
                {"chapter_id": previous["chapter_id"], "title": previous["title"]} if previous else None
            ),
            "next_chapter": (
                {"chapter_id": following["chapter_id"], "title": following["title"]} if following else None
            ),
        }

    def get_chapters(self) -> list[dict[str, Any]]:
        return [
            {
                key: chapter[key]
                for key in (
                    "chapter_id",
                    "chapter_number",
                    "title",
                    "summary",
                    "headings",
                    "source_file",
                    "source_path",
                    "cards",
                )
            }
            for chapter in self._load()
        ]

    def get_course_info(self) -> dict[str, Any]:
        chapters = self._load()
        return {
            "skill_id": self.skill_id,
            "title": "iPAS 淨零碳規劃師",
            "platform_name": "AI Learning Platform",
            "eyebrow": "iPAS 淨零碳規劃師學習平台",
            "headline": "準備 iPAS，從淨零碳規劃核心開始",
            "description": "依序完成八章課程，搭配章節圖卡掌握氣候治理、碳管理與國際標準。",
            "chapter_count": len(chapters),
            "card_count": sum(len(chapter["cards"]) for chapter in chapters),
            "first_chapter_id": chapters[0]["chapter_id"],
        }

    def get_chapter(self, chapter: int | str) -> dict[str, Any]:
        chapters = self._load()
        number = self._chapter_number(chapter)
        payload = dict(chapters[number - 1])
        payload.update(self._navigation(chapters, number - 1))
        return payload

    @staticmethod
    def _search_terms(query: str) -> list[str]:
        terms: list[str] = []
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*|[\u4e00-\u9fff]+", query.casefold()):
            if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 4:
                terms.extend(token[index : index + size] for size in (2, 3, 4) for index in range(len(token) - size + 1))
            else:
                terms.append(token)
        ignored = {"什麼", "怎麼", "如何", "請問", "解釋", "介紹", "內容", "課程", "一下"}
        return list(dict.fromkeys(term for term in terms if term and term not in ignored))

    @staticmethod
    def _excerpt(markdown: str, query: str, limit: int = 220) -> str:
        plain = IpasNetZeroPlannerSkill._plain_text(markdown)
        terms = IpasNetZeroPlannerSkill._search_terms(query)
        lowered = plain.casefold()
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        start = max(0, min(positions) - 70) if positions else 0
        excerpt = plain[start : start + limit].strip()
        return ("…" if start else "") + excerpt + ("…" if start + limit < len(plain) else "")

    def search(self, query: str) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        terms = self._search_terms(query)
        if not terms:
            return []
        results = []
        for chapter in self._load():
            title = chapter["title"].casefold()
            body = self._plain_text(chapter["markdown"]).casefold()
            heading_text = " ".join(chapter["headings"]).casefold()
            score = sum(
                (8 if term in title else 0) + (4 if term in heading_text else 0) + min(body.count(term), 5)
                for term in terms
                if term
            )
            if score:
                results.append(
                    {
                        "chapter_id": chapter["chapter_id"],
                        "chapter_number": chapter["chapter_number"],
                        "title": chapter["title"],
                        "excerpt": self._excerpt(chapter["markdown"], query),
                        "score": score,
                        "source_path": chapter["source_path"],
                        "cards": chapter["cards"],
                    }
                )
        return sorted(results, key=lambda item: (-item["score"], item["chapter_number"]))

    def query_concept(self, query: str) -> dict[str, Any] | None:
        results = self.search(query)
        if not results:
            return None
        result = results[0]
        chapter = self.get_chapter(result["chapter_id"])
        return {
            "knowledge_id": chapter["chapter_id"].upper(),
            "chapter_id": chapter["chapter_id"],
            "title": chapter["title"],
            "definition": chapter["summary"],
            "plain_explanation": result["excerpt"],
            "key_points": chapter["headings"][:8] or [chapter["summary"]],
            "common_confusions": [],
            "source_references": [
                {"source_id": chapter["chapter_id"].upper(), "section": chapter["title"], "locator": chapter["source_path"]}
            ],
            "cards": chapter["cards"],
        }

    def get_key_points(self) -> list[dict[str, Any]]:
        return [
            {
                "knowledge_id": chapter["chapter_id"].upper(),
                "title": chapter["title"],
                "key_points": chapter["headings"][:8] or [chapter["summary"]],
                "source_references": [
                    {"source_id": chapter["chapter_id"].upper(), "section": chapter["title"], "locator": chapter["source_path"]}
                ],
                "cards": chapter["cards"],
            }
            for chapter in self._load()
        ]

    def _question(self, number: int) -> dict[str, Any]:
        chapters = self._load()
        target = chapters[number - 1]
        choices = [chapters[(number - 1 + offset) % len(chapters)] for offset in range(4)]
        rotation = (number - 1) % 4
        choices = choices[rotation:] + choices[:rotation]
        letters = "ABCD"
        correct = letters[choices.index(target)]
        return {
            "question_id": f"NZ-Q{number:03d}",
            "topic_code": target["chapter_id"].upper(),
            "question": f"「{target['summary']}」主要屬於哪一章？",
            "options": {letter: item["title"] for letter, item in zip(letters, choices)},
            "correct_answer": correct,
            "explanation": f"這段內容出自{target['title']}。",
            "difficulty": "easy",
            "question_type": "single_choice_generated_from_chapter",
            "source_references": [
                {"source_id": target["chapter_id"].upper(), "section": target["title"], "locator": target["source_path"]}
            ],
            "review_status": "generated_from_processed_material",
        }

    def get_random_question(self) -> dict[str, Any]:
        question = self._question(self.rng.randint(1, CHAPTER_COUNT))
        return {key: value for key, value in question.items() if key not in {"correct_answer", "explanation"}}

    def get_questions(self) -> list[dict[str, Any]]:
        return [
            {
                key: value
                for key, value in self._question(number).items()
                if key not in {"correct_answer", "explanation"}
            }
            for number in range(1, CHAPTER_COUNT + 1)
        ]

    def submit_answer(self, question_id: str, selected_answer: str) -> dict[str, Any]:
        match = re.fullmatch(r"NZ-Q00([1-8])", (question_id or "").strip().upper())
        if not match:
            raise ValueError(f"找不到題號：{question_id}")
        selected = (selected_answer or "").strip().upper().strip("()（）")
        question = self._question(int(match.group(1)))
        return {
            "question_id": question["question_id"],
            "selected_answer": selected,
            "correct": selected == question["correct_answer"],
            "correct_answer": question["correct_answer"],
            "explanation": question["explanation"],
            "source_references": question["source_references"],
        }

    def get_sources(self) -> dict[str, Any]:
        chapters = self._load()
        return {
            "sources": [
                {
                    "source_id": chapter["chapter_id"].upper(),
                    "title": chapter["title"],
                    "filename": chapter["source_file"],
                    "source_role": "processed_course_chapter",
                    "sha256": chapter["sha256"],
                    "parse_status": "success",
                }
                for chapter in chapters
            ],
            "chapter": {
                "title": "iPAS 淨零碳規劃師課程",
                "topic_code": "CH01-CH08",
                "page_or_section_reference": [chapter["source_path"] for chapter in chapters],
            },
        }

    @staticmethod
    def _reference_lines(references: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"- {reference['source_id']}｜{reference['section']}｜{reference['locator']}"
            for reference in references
        )

    def answer(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "請輸入想查詢的淨零碳主題，或輸入「章節列表」。"
        try:
            submission = re.search(r"(NZ-Q00[1-8]).*?(?:答案|選)\s*[:：]?\s*\(?([A-D])\)?", question, re.I)
            if submission:
                result = self.submit_answer(submission.group(1), submission.group(2))
                verdict = "答對了" if result["correct"] else "答錯了"
                return (
                    f"{verdict}，正確答案是 {result['correct_answer']}。\n\n"
                    f"解析：{result['explanation']}\n\n來源：\n{self._reference_lines(result['source_references'])}"
                )
            if any(term in question for term in ("隨機題", "測驗", "出題")):
                item = self.get_random_question()
                options = "\n".join(f"({key}) {value}" for key, value in item["options"].items())
                return f"{item['question_id']}\n{item['question']}\n{options}\n\n請用「{item['question_id']} 答案 A」的格式作答。"
            if any(term in question for term in ("來源", "教材")):
                payload = self.get_sources()
                return "iPAS 淨零碳規劃師教材來源：\n" + "\n".join(
                    f"- {item['source_id']}｜{item['title']}｜{item['filename']}" for item in payload["sources"]
                )
            if any(term in question for term in ("章節列表", "所有章節", "課程目錄", "首頁")):
                return "iPAS 淨零碳規劃師課程\n\n" + "\n".join(
                    f"{item['chapter_id'].upper()}｜{item['title']}｜圖卡 {len(item['cards'])} 張"
                    for item in self.get_chapters()
                )
            chapter_match = re.search(r"(?:第\s*)?([一二三四五六七八1-8])\s*章|ch\s*0?([1-8])", question, re.I)
            if chapter_match:
                chinese_numbers = "一二三四五六七八"
                token = chapter_match.group(1) or chapter_match.group(2)
                number = chinese_numbers.index(token) + 1 if token in chinese_numbers else int(token)
                chapter = self.get_chapter(number)
                navigation = []
                if chapter["previous_chapter"]:
                    navigation.append(f"上一章：{chapter['previous_chapter']['title']}")
                if chapter["next_chapter"]:
                    navigation.append(f"下一章：{chapter['next_chapter']['title']}")
                cards = "、".join(chapter["cards"]) if chapter["cards"] else "本章無圖卡"
                return (
                    f"{chapter['title']}\n\n{chapter['markdown']}\n\n"
                    f"圖卡：{cards}\n\n" + "｜".join(navigation)
                )
            concept = self.query_concept(question)
            if not concept:
                return "查不到相符的淨零碳課程內容，請換一個關鍵字，或輸入「章節列表」。"
            points = "\n".join(f"- {point}" for point in concept["key_points"])
            return (
                f"{concept['title']}\n\n{concept['plain_explanation']}\n\n章節重點：\n{points}\n\n"
                f"來源：\n{self._reference_lines(concept['source_references'])}"
            )
        except (DataUnavailableError, ValueError) as exc:
            return str(exc)


_default_skill = IpasNetZeroPlannerSkill()


def configure(_ask_gpt_func: Callable[[str, str], str]) -> None:
    """Tutor adapter hook; local processed materials are used deterministically."""


def answer(question: str) -> str:
    return _default_skill.answer(question)


def query_concept(query: str) -> dict[str, Any] | None:
    return _default_skill.query_concept(query)


def get_key_points() -> list[dict[str, Any]]:
    return _default_skill.get_key_points()


def get_random_question() -> dict[str, Any]:
    return _default_skill.get_random_question()


def get_questions() -> list[dict[str, Any]]:
    return _default_skill.get_questions()


def submit_answer(question_id: str, selected_answer: str) -> dict[str, Any]:
    return _default_skill.submit_answer(question_id, selected_answer)


def get_sources() -> dict[str, Any]:
    return _default_skill.get_sources()


def get_chapters() -> list[dict[str, Any]]:
    return _default_skill.get_chapters()


def get_course_info() -> dict[str, Any]:
    return _default_skill.get_course_info()


def get_chapter(chapter: int | str) -> dict[str, Any]:
    return _default_skill.get_chapter(chapter)


def search(query: str) -> list[dict[str, Any]]:
    return _default_skill.search(query)
