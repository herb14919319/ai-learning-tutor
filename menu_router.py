import logging
from dataclasses import dataclass
from pathlib import Path

from linebot.v3.messaging import ImageMessage, ReplyMessageRequest, TextMessage


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MenuResponse:
    text: str
    image_filename: str | None = None


MENU_COMMANDS: dict[str, MenuResponse] = {
    "AI地圖": MenuResponse(
        image_filename="ai_map.png",
        text=(
            "這是 AI 學習地圖。\n"
            "你可以從 ML、DL、LLM、Agent 慢慢往下探索。\n\n"
            "想了解更多，可以直接問我：\n"
            "「我該怎麼開始學 AI？」"
        ),
    ),
    "ML基礎": MenuResponse(
        image_filename="ml_vs_dl.png",
        text=(
            "這是機器學習的基礎入口。\n"
            "ML 的核心是：讓模型從資料中學出規律。\n\n"
            "你可以接著問：\n"
            "「監督式學習是什麼？」\n"
            "「回歸和分類差在哪？」"
        ),
    ),
    "DL基礎": MenuResponse(
        image_filename="deep_learning.png",
        text=(
            "這是深度學習的基礎入口。\n"
            "DL 可以理解成使用多層神經網路，讓模型學出更抽象的特徵。\n\n"
            "你可以接著問：\n"
            "「神經網路是什麼？」\n"
            "「深度學習和機器學習差在哪？」"
        ),
    ),
    "LLM介紹": MenuResponse(
        image_filename="llm_training.png",
        text=(
            "這是大型語言模型 LLM 的入門入口。\n"
            "LLM 的核心是：從大量文字中學習語言、知識與推理模式。\n\n"
            "你可以接著問：\n"
            "「LLM 是怎麼訓練的？」\n"
            "「GPT 和一般 AI 有什麼差別？」"
        ),
    ),
    "Agent介紹": MenuResponse(
        image_filename="agent_intro.png",
        text=(
            "這是 AI Agent 的入門入口。\n"
            "Agent 不只是回答問題，而是能理解目標、使用工具、記住狀態，並協助完成任務。\n\n"
            "你可以接著問：\n"
            "「AI Agent 和 ChatGPT 差在哪？」\n"
            "「Tool Calling 是什麼？」"
        ),
    ),
    "我要問問題": MenuResponse(
        text=(
            "歡迎直接問我 AI 相關問題。\n\n"
            "例如：\n"
            "「什麼是 RAG？」\n"
            "「什麼是 MCP？」\n"
            "「AI Agent 怎麼設計？」\n"
            "「我想學機器學習，該從哪裡開始？」"
        ),
    ),
}


def _normalize(text: str) -> str:
    return text.strip()


def is_menu_command(text: str) -> bool:
    return _normalize(text) in MENU_COMMANDS


def _asset_url(public_base_url: str, filename: str) -> str:
    return f"{public_base_url.rstrip('/')}/assets/{filename}"


def handle_menu_command(
    text: str,
    line_bot_api,
    reply_token: str,
    public_base_url: str,
    assets_dir: str | Path = "assets",
) -> bool:
    response = MENU_COMMANDS.get(_normalize(text))
    if response is None:
        return False

    messages = []
    if response.image_filename:
        image_path = Path(assets_dir) / response.image_filename
        if image_path.exists() and public_base_url:
            image_url = _asset_url(public_base_url, response.image_filename)
            messages.append(
                ImageMessage(
                    originalContentUrl=image_url,
                    previewImageUrl=image_url,
                )
            )
        else:
            logger.warning(
                "Skipping Rich Menu image reply; image_path=%s exists=%s public_base_url=%s",
                image_path,
                image_path.exists(),
                bool(public_base_url),
            )

    text_message = TextMessage(text=response.text)
    messages.append(text_message)

    try:
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )
    except Exception:
        if len(messages) == 1:
            logger.exception("LINE Rich Menu text reply failed")
            return True

        logger.exception("LINE Rich Menu image reply failed; retrying text-only reply")
        try:
            line_bot_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[text_message])
            )
        except Exception:
            logger.exception("LINE Rich Menu text fallback reply failed")

    return True
