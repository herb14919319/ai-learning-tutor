from __future__ import annotations

import re


AI_DOMAIN_TERMS = (
    "MCP",
    "RAG",
    "Agent",
    "AI Agent",
    "Tool Calling",
    "Function Calling",
    "LLM",
    "Prompt",
    "Embedding",
    "Vector DB",
    "Vector Database",
)

MICROSOFT_MCP_TERMS = (
    "Microsoft",
    "Microsoft Certified Professional",
    "certification",
    "certificate",
    "certified",
    "exam",
    "Windows",
    "Azure",
    "Office",
    "微軟",
    "證照",
    "認證",
    "考試",
)


def _contains_ascii_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text.lower()))


def _contains_term(text: str, term: str) -> bool:
    return _contains_ascii_term(text, term) if term.isascii() else term in text


def contains_ai_domain_term(user_message: str) -> bool:
    text = user_message or ""
    return any(_contains_term(text, term) for term in AI_DOMAIN_TERMS)


def has_microsoft_mcp_context(user_message: str) -> bool:
    text = user_message or ""
    return any(_contains_term(text, term) for term in MICROSOFT_MCP_TERMS)


def build_ai_acronym_disambiguation_prompt(user_message: str) -> str:
    """Return a compact prompt hint for ambiguous AI-domain acronyms."""
    text = user_message or ""
    has_mcp = _contains_ascii_term(text, "MCP")
    has_microsoft_phrase = _contains_term(text, "Microsoft Certified Professional")

    if has_microsoft_phrase:
        return (
            "縮寫消歧：使用者明確提到 Microsoft Certified Professional。"
            "請解釋為 Microsoft Certified Professional，中文可稱為微軟認證專家。"
        )

    if has_mcp and has_microsoft_mcp_context(text):
        return (
            "縮寫消歧：使用者提到 MCP，且問題含有 Microsoft/微軟、證照、認證、考試、"
            "Windows、Azure 或 Office 等線索時，MCP 可以解釋為 Microsoft Certified Professional"
            "（微軟認證專家）。"
        )

    if has_mcp:
        return (
            "縮寫消歧：使用者提到 MCP，且沒有明確的 Microsoft/微軟、證照、認證、考試、"
            "Windows、Azure 或 Office 線索。請優先以 AI Agent 領域回答："
            "「在 AI Agent 領域中，MCP 通常指 Model Context Protocol」。"
            "不要把 MCP 優先解釋為 Microsoft Certified Professional。"
        )

    if contains_ai_domain_term(text):
        terms = ", ".join(AI_DOMAIN_TERMS)
        return (
            f"縮寫消歧：使用者問題包含 AI/Agent 領域常見詞（例如 {terms}）。"
            "請優先用 AI、LLM、RAG、Agent 或工具呼叫脈絡理解縮寫；"
            "遇到縮寫詞時，先說明「在 AI Agent 領域中，...通常指...」，再補充其他可能含義。"
        )

    return ""
