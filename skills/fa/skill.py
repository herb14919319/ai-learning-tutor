from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

from skills.fa.retriever import FaRetriever


logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
BOUNDARY_MESSAGE = "目前 FA 功能查詢小幫手只提供操作手冊導覽，無法查詢正式 FA 系統中的即時資料。"
NO_DATA_MESSAGE = "操作手冊中未找到足夠資訊"
REALTIME_ENTITIES = ("包裹", "管理費", "訪客", "報修", "公設", "繳款", "QR Code", "qr code")
REALTIME_TERMS = ("即時", "現在", "目前", "狀態", "進度", "剩餘", "有沒有", "是否已", "查詢", "多少")
REQUIRED_FIELDS = ("功能名稱：", "適用端別：", "功能位置：", "操作步驟：", "注意事項：", "手冊頁碼：", "資料不足說明：")


class FaSkill:
    skill_id = "fa"

    def __init__(self, ask_gpt: Callable[[str, str], str], *, retriever: FaRetriever | None = None):
        self.ask_gpt = ask_gpt
        self.retriever = retriever or FaRetriever(ROOT / "config.json", ROOT / "knowledge" / "index.json")
        self.prompt_template = (ROOT / "prompt.md").read_text(encoding="utf-8")

    def answer(self, question: str) -> str:
        normalized = (question or "").strip()
        if not normalized:
            return self._no_data_answer()
        if self._is_realtime_query(normalized):
            return self._boundary_answer(normalized)

        results = self.retriever.search(normalized)
        if not results:
            return self._no_data_answer()

        context = self.retriever.format_context(results)
        system_prompt = self.prompt_template.replace("{{context}}", context)
        user_prompt = f"使用者問題：{normalized}"
        answer = (self.ask_gpt(system_prompt, user_prompt) or "").strip()
        if not answer:
            return self._no_data_answer()

        pages = sorted({result.metadata.get("page_start") for result in results if result.metadata.get("page_start")})
        return self._enforce_response_contract(answer, pages)

    @staticmethod
    def _is_realtime_query(question: str) -> bool:
        lowered = question.lower()
        return any(entity.lower() in lowered for entity in REALTIME_ENTITIES) and any(
            term.lower() in lowered for term in REALTIME_TERMS
        )

    @staticmethod
    def _empty_fields(function_name: str, data_note: str) -> str:
        return "\n".join(
            (
                f"功能名稱：{function_name}",
                "適用端別：操作手冊中未找到足夠資訊",
                "功能位置：操作手冊中未找到足夠資訊",
                "操作步驟：操作手冊中未找到足夠資訊",
                "注意事項：操作手冊中未找到足夠資訊",
                "手冊頁碼：操作手冊中未找到足夠資訊",
                f"資料不足說明：{data_note}",
            )
        )

    def _no_data_answer(self) -> str:
        return self._empty_fields(NO_DATA_MESSAGE, NO_DATA_MESSAGE)

    def _boundary_answer(self, question: str) -> str:
        function_name = re.sub(r"[？?]$", "", question).strip() or "即時資料查詢"
        return self._empty_fields(function_name, BOUNDARY_MESSAGE)

    @staticmethod
    def _enforce_response_contract(answer: str, pages: list[int]) -> str:
        allowed_pages = ", ".join(map(str, pages)) or NO_DATA_MESSAGE
        lines = answer.splitlines()
        normalized_lines = []
        page_field_found = False
        for line in lines:
            if line.strip().startswith("手冊頁碼："):
                normalized_lines.append(f"手冊頁碼：{allowed_pages}")
                page_field_found = True
            else:
                normalized_lines.append(line)

        normalized = "\n".join(normalized_lines).strip()
        missing = []
        for field in REQUIRED_FIELDS:
            if field == "手冊頁碼：" and page_field_found:
                continue
            if field not in normalized:
                value = allowed_pages if field == "手冊頁碼：" else NO_DATA_MESSAGE
                missing.append(f"{field}{value}")
        if missing:
            normalized = f"{normalized}\n" + "\n".join(missing)
        return normalized
