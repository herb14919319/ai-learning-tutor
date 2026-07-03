from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from models import create_model_client

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 12000
KB_TIMEOUT_SECONDS = 20

ROOT = Path(__file__).resolve().parents[1]
SKILL_REPO = Path(__file__).resolve().parent / "hung-yi-lee-skill"
KB_SCRIPT = SKILL_REPO / "scripts" / "hungyi_kb.py"

_ask_gpt: Callable[[str, str], str] | None = None


def configure(ask_gpt_func: Callable[[str, str], str]) -> None:
    """Provide the app's GPT caller so answer() can stay a simple tool API."""
    global _ask_gpt
    _ask_gpt = ask_gpt_func


def ask_gpt(system_prompt: str, user_prompt: str) -> str:
    """Fallback GPT caller used when the host app has not configured one."""
    if _ask_gpt:
        return _ask_gpt(system_prompt, user_prompt)

    client = create_model_client()
    if not client:
        provider = os.getenv("MODEL_PROVIDER", "openai").strip().lower()
        raise RuntimeError(f"{provider} model API is not configured")
    return client.complete(system_prompt, user_prompt)


def answer(question: str) -> str:
    """
    Answer an AI/ML question through the Hung-Yi Lee knowledge-base skill.

    Query order:
    1. graph query for structural navigation
    2. search only when graph output is thin or missing
    3. grounded prompt into ask_gpt()
    4. fallback to ordinary GPT teaching if retrieval fails
    """
    question = question.strip()
    if not question:
        return ""

    try:
        context = build_grounded_context(question)
        system_prompt = build_hungyi_system_prompt(context)
        user_prompt = f"學生問題：{question}"
        return ask_gpt(system_prompt, user_prompt)
    except Exception:
        logger.exception("Hung-Yi Lee skill retrieval failed; falling back to general GPT teaching")
        return fallback_answer(question)


def build_grounded_context(question: str) -> str:
    parts = []
    graph_output = ""

    try:
        graph_output = run_kb(["graph", "query", question])
        parts.append(format_context_block("Knowledge Graph Query", graph_output))
    except Exception as exc:
        logger.warning("Hung-Yi graph query failed; trying transcript search: %s", exc)

    if graph_result_is_insufficient(graph_output):
        search_output = run_kb(["search", question, "--limit", "8"])
        parts.append(format_context_block("Transcript Search", search_output))

    context = "\n\n".join(part for part in parts if part.strip())
    if not context.strip():
        raise RuntimeError("No grounded context returned from Hung-Yi Lee skill")
    return context[:MAX_CONTEXT_CHARS]


def run_kb(args: list[str]) -> str:
    if not KB_SCRIPT.exists():
        raise FileNotFoundError(f"Knowledge-base script not found: {KB_SCRIPT}")

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    completed = subprocess.run(
        [sys.executable, str(KB_SCRIPT), *args],
        cwd=SKILL_REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=KB_TIMEOUT_SECONDS,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part.strip()).strip()
    if completed.returncode != 0:
        raise RuntimeError(f"hungyi_kb.py {' '.join(args)} failed: {output}")
    return output


def graph_result_is_insufficient(output: str) -> bool:
    normalized = output.lower()
    if not output.strip():
        return True
    if "no matching nodes found" in normalized or "no graph found" in normalized:
        return True

    node_lines = [line for line in output.splitlines() if line.lstrip().startswith("•")]
    return len(node_lines) < 3


def format_context_block(title: str, body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    return f"## {title}\n\n{body}"


def build_hungyi_system_prompt(grounded_context: str) -> str:
    return f"""你是 AI 學習助教。請用「李宏毅式教學方法」回答，但不要扮演李宏毅教授本人。

必須遵守：
- sound like teaching method, not identity roleplay；不要說你是李宏毅教授。
- intuition first：先講直覺與學生可以抓住的 punchline。
- black-box framing before mechanism：先把系統當黑盒子，講 input、output、目標，再打開機制。
- transcript-grounded when possible：有檢索到逐字稿或影片脈絡時，優先依據它；可以說「這個脈絡裡有提到...」。
- 如果 grounded context 不足以支持某個細節，要明確說「這部分資料不足」，不要亂補來源或課程內容。
- 回答使用繁體中文；必要技術詞保留英文並立刻解釋。
- 用教學語氣，不用身分扮演，不做官方授權或本人背書的宣稱。

Grounded context:

{grounded_context or "（沒有可用的 skill 查詢結果。）"}
"""


def build_fallback_system_prompt() -> str:
    return """你是 AI 學習助教。請用一般 GPT 教學回答。

請遵守：
- 先講直覺，再講機制。
- 先用 black-box 方式說 input、output、目標，再進入細節。
- 不要聲稱自己是李宏毅教授或任何真實人物。
- 如果不確定，明確說不確定，不要亂補來源。
- 使用繁體中文。
"""


def fallback_answer(question: str) -> str:
    try:
        return ask_gpt(build_fallback_system_prompt(), f"學生問題：{question}")
    except Exception:
        logger.exception("Fallback GPT answer failed")
        return "抱歉，我剛剛查詢 skill 和一般 GPT 回答都遇到問題。請稍後再試一次。"
