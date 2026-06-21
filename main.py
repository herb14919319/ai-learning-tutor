import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from openai import OpenAI, OpenAIError


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_NAME = "AI Learning 助教"
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_LINE_TEXT_LENGTH = 4500
SKILL_PATH = Path(__file__).resolve().parent / "skills" / "hung-yi-lee-skill" / "SKILL.md"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

app = Flask(__name__)
app.json.ensure_ascii = False

line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def load_skill_context() -> str:
    try:
        return SKILL_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Skill file not found: %s", SKILL_PATH)
        return ""
    except OSError:
        logger.exception("Failed to read skill file: %s", SKILL_PATH)
        return ""


def build_system_prompt(skill_context: str) -> str:
    prompt = f"""你是「{APP_NAME}」。

你的任務是協助使用者學習 AI、機器學習、深度學習、Python、AI Agent、RAG、MCP 等主題。

你可以參考已載入的 skill 內容與教學風格，但你不可聲稱自己是李宏毅教授本人。
你不可宣稱本服務為李宏毅教授、台大或任何教育機構官方服務。
如果參考 skill 內容，只能說「依據學習助教的教學風格/脈絡」，不要宣稱官方授權。

回答時請先講核心觀念，再用生活化比喻，必要時補簡單範例。
不確定的事情要明確說不確定。
不要編造來源、課程內容或授權資訊。
請以「AI 學習助教」身份提供協助。
"""

    if skill_context:
        prompt += f"\n以下是可參考的學習助教 skill 內容：\n\n{skill_context}"
    else:
        prompt += "\n目前沒有載入 skill 內容，請以一般 AI 學習助教身份回答。"

    return prompt


def truncate_for_line(text: str) -> str:
    if len(text) <= MAX_LINE_TEXT_LENGTH:
        return text
    return text[:MAX_LINE_TEXT_LENGTH].rstrip() + "\n\n（回覆已因 LINE 單則訊息長度限制截斷）"


def help_text() -> str:
    return (
        f"你好，我是「{APP_NAME}」。\n\n"
        "你可以直接問我 AI、機器學習、深度學習、Python、AI Agent、RAG、MCP 等問題。\n\n"
        "範例：\n"
        "1. 什麼是 Transformer？\n"
        "2. RAG 跟微調有什麼差別？\n"
        "3. 可以用生活化比喻解釋梯度下降嗎？\n\n"
        "提醒：本服務是 AI 學習工具，非任何教師、學校或教育機構官方帳號。"
    )


def generate_ai_reply(user_text: str, *, truncate: bool = True) -> str:
    if not openai_client:
        return "目前 OpenAI API 尚未設定完成，請稍後再試。"

    skill_context = load_skill_context()
    system_prompt = build_system_prompt(skill_context)

    try:
        response = openai_client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        reply = response.output_text.strip()
    except OpenAIError:
        logger.exception("OpenAI API request failed")
        return "抱歉，我剛剛連線到 AI 服務時遇到問題。請稍後再試一次。"
    except Exception:
        logger.exception("Unexpected OpenAI response error")
        return "抱歉，我剛剛產生回覆時遇到問題。請稍後再試一次。"

    if not reply:
        return "抱歉，我這次沒有產生有效回覆。請換個問法再試一次。"

    if truncate:
        return truncate_for_line(reply)
    return reply


def reply_text(reply_token: str, text: str) -> None:
    try:
        with ApiClient(line_configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=truncate_for_line(text))],
                )
            )
    except Exception:
        logger.exception("LINE reply API failed")


@app.get("/")
def health_check():
    return f"{APP_NAME} service is running."


@app.get("/test")
def test_mode():
    question = request.args.get("question", "").strip()

    if not question:
        return jsonify({"error": "Missing required query parameter: question"}), 400

    answer = generate_ai_reply(question, truncate=False)
    return jsonify(
        {
            "question": question,
            "answer": answer,
            "model": OPENAI_MODEL,
        }
    )


@app.post("/callback")
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE signature")
        abort(400)
    except Exception:
        logger.exception("Webhook handler failed")

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    user_text = event.message.text.strip()

    if user_text.lower() == "/help":
        reply_text(event.reply_token, help_text())
        return

    reply = generate_ai_reply(user_text)
    reply_text(event.reply_token, reply)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
