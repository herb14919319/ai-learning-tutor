from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]+|[\u3400-\u9fff]{2,}")
SIDE_TERMS = {
    "management": ("管理端", "管理員", "管理者", "管委", "後台"),
    "resident": ("住戶端", "居民端", "我是住戶"),
}


@dataclass(frozen=True)
class SearchResult:
    score: float
    text: str
    metadata: dict


class FaRetriever:
    def __init__(self, config_path: Path, index_path: Path):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.chunks = index.get("chunks", [])
        self.max_results = int(self.config.get("max_results", 6))
        self.min_score = float(self.config.get("min_score", 3.0))

    def search(self, question: str) -> list[SearchResult]:
        query = self._expand_query(question)
        requested_side = self._requested_side(question)
        requested_modules = self._requested_modules(question)
        query_tokens = self._tokens(query)
        query_bigrams = self._bigrams(query)
        scored = []

        for chunk in self.chunks:
            metadata = chunk.get("metadata", {})
            text = chunk.get("text", "")
            side = metadata.get("user_side", "both")
            if requested_side and side not in {requested_side, "both"}:
                continue

            module = str(metadata.get("module", ""))
            haystack = f"{module} {metadata.get('section', '')} {text}".lower()
            score = 0.0
            if module in requested_modules:
                score += 8.0
            for token in query_tokens:
                if token in haystack:
                    score += min(3.0, 1.0 + len(token) / 4)
            score += min(4.0, sum(1 for pair in query_bigrams if pair in haystack) * 0.25)
            if requested_side and side == requested_side:
                score += 1.5
            if score > 0:
                scored.append(SearchResult(score=score, text=text, metadata=metadata))

        scored.sort(key=lambda item: (-item.score, item.metadata.get("page_start", 0)))
        selected = self._select_diverse_results(scored, requested_modules)
        if not selected or selected[0].score < self.min_score:
            return []
        return selected

    def format_context(self, results: list[SearchResult]) -> str:
        blocks = []
        for result in results:
            meta = result.metadata
            page_start = meta.get("page_start")
            page_end = meta.get("page_end")
            pages = str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
            blocks.append(
                "\n".join(
                    (
                        f"[手冊頁碼：{pages}]",
                        f"模組：{meta.get('module', '未知')}",
                        f"章節：{meta.get('section', '未知')}",
                        f"適用端別：{meta.get('user_side', 'both')}",
                        f"來源：{meta.get('source_file', '')}",
                        result.text,
                    )
                )
            )
        return "\n\n---\n\n".join(blocks)

    def _expand_query(self, question: str) -> str:
        expanded = [question.strip()]
        compact = re.sub(r"\s+", "", question)
        for key, aliases in self.config.get("query_aliases", {}).items():
            if key in compact or any(alias in compact for alias in aliases):
                expanded.extend(aliases)
        return " ".join(expanded)

    def _requested_modules(self, query: str) -> set[str]:
        compact = re.sub(r"\s+", "", query).lower()
        modules = set()
        for module, aliases in self.config.get("module_aliases", {}).items():
            if module.lower() in compact or any(alias.lower() in compact for alias in aliases):
                modules.add(module)
        return modules

    @staticmethod
    def _requested_side(question: str) -> str | None:
        for side, terms in SIDE_TERMS.items():
            if any(term in question for term in terms):
                return side
        if re.search(r"住戶(?:要|如何|怎麼|可以|能否)", question):
            return "resident"
        return None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        tokens = {token.lower() for token in TOKEN_PATTERN.findall(text)}
        for token in list(tokens):
            if any("\u3400" <= char <= "\u9fff" for char in token) and len(token) > 2:
                tokens.update(token[i : i + 2] for i in range(len(token) - 1))
        return {token for token in tokens if len(token) >= 2}

    @staticmethod
    def _bigrams(text: str) -> set[str]:
        compact = re.sub(r"[^A-Za-z0-9\u3400-\u9fff]", "", text.lower())
        return {compact[i : i + 2] for i in range(max(0, len(compact) - 1))}

    def _select_diverse_results(self, scored: list[SearchResult], requested_modules: set[str]) -> list[SearchResult]:
        if not scored:
            return []
        selected = []
        seen_pages = set()
        modules = requested_modules or {scored[0].metadata.get("module", "")}
        per_module_limit = max(2, self.max_results // max(1, len(modules)))
        module_counts = {}
        for result in scored:
            module = result.metadata.get("module", "")
            if requested_modules and module not in requested_modules:
                continue
            page = result.metadata.get("page_start")
            if page in seen_pages or module_counts.get(module, 0) >= per_module_limit:
                continue
            selected.append(result)
            seen_pages.add(page)
            module_counts[module] = module_counts.get(module, 0) + 1
            if len(selected) >= self.max_results:
                break
        return selected
