# AI Learning 助教 LINE Bot MVP

> **Tree／小樹聊天模式狀態：已退休並移除（Retired）。** AI Tutor 不再提供 Tree 聊天模式、Skill Selector 或快捷入口，聊天 runtime 程式碼與測試已移除；`/離開`、`/李教授` 仍回覆原本的「回到一般 AI Tutor」訊息以維持相容。Little Tree 網頁提示詞導覽（`/little-tree`）與 Office AI（`/office-ai`）維持不變。

這是一個 Python Flask LINE Bot MVP，正式環境部署目標為 **Render**（見下方「Render 部署（正式環境）」）。

使用者傳 LINE 訊息給 Bot 後，Flask webhook 會接收訊息，讀取本地 `skills/hung-yi-lee-skill/SKILL.md` 作為 system context，呼叫 OpenAI Responses API，最後將 GPT 回覆傳回 LINE。

LINE Bot 帳號名稱預計為「AI Learning 助教」。

## 專案結構

```text
ai-learning-tutor/
├── main.py
├── requirements.txt
├── Dockerfile
├── .gitignore
├── README.md
└── skills/
    └── hung-yi-lee-skill/
        └── SKILL.md
```

## 環境變數

服務會讀取以下環境變數：

```bash
OPENAI_API_KEY="你的 OpenAI API Key"
LINE_CHANNEL_ACCESS_TOKEN="你的 LINE Channel Access Token"
LINE_CHANNEL_SECRET="你的 LINE Channel Secret"
OPENAI_MODEL="gpt-4.1-mini"
PORT="8080"
PUBLIC_BASE_URL="https://your-public-service-url"
```

`OPENAI_MODEL` 可省略，預設使用 `gpt-4.1-mini`。
`PUBLIC_BASE_URL` 用於產生 LINE Rich Menu 圖片網址，例如 `https://your-service.onrender.com/assets/ai_map.png`。若未設定，服務會用目前 request 的 host 自動產生；部署到 Render 時建議明確設定為服務公開 HTTPS URL。

## 本機 .env

本機開發時，請在專案根目錄建立 `.env`：

```env
OPENAI_API_KEY=你的 OpenAI API Key
LINE_CHANNEL_ACCESS_TOKEN=你的 LINE Channel Access Token
LINE_CHANNEL_SECRET=你的 LINE Channel Secret
OPENAI_MODEL=gpt-4.1-mini
PORT=8080
PUBLIC_BASE_URL=https://your-public-service-url
```

`main.py` 啟動時會透過 `python-dotenv` 自動載入 `.env`。如果同一個變數已經存在於系統環境變數中，系統環境變數會保留原值，不會被 `.env` 覆蓋。這讓本機 `.env` 與 Render 的環境變數設定可以相容。

`.env` 已列在 `.gitignore`，請不要將 API key 或 LINE secret commit 到版本庫。

## Clone Skill Repo

如果尚未下載 skill，請在專案根目錄執行：

```bash
git clone https://github.com/voidful/hung-yi-lee-skill.git skills/hung-yi-lee-skill
```

若 `skills/hung-yi-lee-skill/SKILL.md` 不存在，服務仍會以一般 AI 學習助教身份回答。

## 本機執行

建立虛擬環境並安裝套件：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell 可使用：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

確認專案根目錄已有 `.env` 後啟動服務：

```bash
python main.py
```

或使用 gunicorn：

```bash
gunicorn --bind :8080 --workers 1 --threads 8 --timeout 120 main:app
```

健康檢查：

```bash
curl http://localhost:8080/
```

## 自動化測試

測試使用標準函式庫 `unittest`，請在 repo 根目錄執行：

```bash
python -m unittest discover -s tests -t .
```

`-t .` 會先載入 `tests/__init__.py`，把 runtime telemetry 導向暫存檔，避免測試寫入受版本控制的 `data/runtime_telemetry.jsonl`。若漏掉 `-t .`，`test_baseline_characterization` 會失敗提醒。正式環境可用 `RUNTIME_TELEMETRY_PATH` 指定 telemetry 檔案位置，未設定時維持 `data/runtime_telemetry.jsonl`。注意：此值在 `runtime_telemetry` 匯入時讀取，早於 `main.py` 載入 `.env`，因此必須設為真正的環境變數（例如 Render 環境變數），寫在 `.env` 不會生效。Telemetry 透過 `runtime_telemetry.get_telemetry_sink()`（預設 `JsonlTelemetrySink`）寫入；學習者短期狀態透過 `memory/learner_state.py` 的 `LearnerStateStore`（預設記憶體內、單一行程）。

## Render 部署（正式環境）

Render 是本專案唯一的正式部署目標。Web Service 的 Build／Start Command、必要環境變數與上線檢查請見 [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md)；每週 Facebook 發文的 Cron 設定與人工核准閘門請見 [docs/FACEBOOK_WEEKLY_PUBLISHING.md](docs/FACEBOOK_WEEKLY_PUBLISHING.md)。

LINE webhook URL 請設定為：

```text
https://your-service.onrender.com/callback
```

## Cloud Run 部署（Legacy／歷史紀錄）

> **Legacy：** 以下為早期 Google Cloud Run 部署方式，僅保留作為歷史紀錄，已不是正式部署目標，也不再維護。正式環境請使用上方的 Render 部署。`.gcloudignore` 亦屬此歷史設定。

請先確認已安裝並登入 Google Cloud CLI，並已設定專案：

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

建置並部署：

```bash
gcloud run deploy ai-learning-tutor \
  --source . \
  --region asia-east1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY="你的 OpenAI API Key",LINE_CHANNEL_ACCESS_TOKEN="你的 LINE Channel Access Token",LINE_CHANNEL_SECRET="你的 LINE Channel Secret",OPENAI_MODEL="gpt-4.1-mini"
```

Cloud Run 會從服務環境變數讀取 `OPENAI_API_KEY`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、`OPENAI_MODEL` 與 `PORT`。Cloud Run 會自動提供 `PORT`，通常不需要手動設定。

部署完成後，Cloud Run 會輸出服務 URL，例如：

```text
https://ai-learning-tutor-xxxxx-uc.a.run.app
```

LINE webhook URL 請設定為：

```text
https://你的-cloud-run-url/callback
```

## LINE Developers Webhook 設定

1. 到 LINE Developers Console 建立或開啟 Messaging API channel。
2. 在 Messaging API 頁面取得 `Channel access token`，設定為 `LINE_CHANNEL_ACCESS_TOKEN`。
3. 在 Basic settings 頁面取得 `Channel secret`，設定為 `LINE_CHANNEL_SECRET`。
4. 將 Webhook URL 設為 Render 服務 URL 加上 `/callback`，例如 `https://your-service.onrender.com/callback`。
5. 啟用 `Use webhook`。
6. 關閉或依需求調整 LINE 官方的 Auto-reply messages，避免與 Bot 回覆重複。
7. 使用 LINE Developers Console 的 Verify 按鈕測試 webhook。

## 使用方式

傳送 `/help` 可取得使用說明。

一般文字訊息會交由 AI Learning 助教回答。第一版只處理文字訊息；圖片、貼圖、語音等訊息會被忽略。

## Rich Menu MVP

LINE Rich Menu 按鈕送出的固定文字會先被 `app/channels/line_menu.py` 攔截，不會進入 LLM，也不會先回覆「助教正在努力思考中...」。

目前支援：

```text
AI地圖
ML基礎
DL基礎
LLM介紹
Agent介紹
我要問問題
```

圖片素材放在 `assets/`，並由 Flask route `/assets/<filename>` 對外提供。LINE `ImageMessage` 需要公開可存取的 `originalContentUrl` 和 `previewImageUrl`，所以部署時請設定：

```bash
PUBLIC_BASE_URL="https://your-render-or-cloud-run-url"
```

本地若要測試圖片網址，可啟動服務後開啟：

```text
http://localhost:8080/assets/ai_map.png
```

若要讓 LINE 在本地也能讀取圖片，需要使用 ngrok、Cloudflare Tunnel 等 HTTPS tunnel，並將 `PUBLIC_BASE_URL` 設為 tunnel URL。

## 免責聲明

本服務為 AI 學習工具，非任何教師、學校或教育機構官方帳號。

本服務可依據學習助教的教學風格/脈絡協助解釋 AI 相關概念，但不宣稱為李宏毅教授、台大或任何教育機構官方服務，也不宣稱取得官方授權。

## Runtime Observability

`/dashboard`, `/observability`, and `/api/runtime/telemetry` expose operational
runtime metrics and are disabled by default. Set `DASHBOARD_API_KEY` or
`OBSERVABILITY_API_KEY`, then call these routes with the `X-Dashboard-Key`
header. LINE webhook, `/web-chat`, `/healthz`, and the public web chat page do
not use this dashboard key.

Runtime telemetry is a lightweight local append-only JSONL log at
`data/runtime_telemetry.jsonl`. It records operational fields such as entrypoint,
provider, model, status, latency, token counts, fallback status, and error type.
This telemetry is not conversational memory: it is not used for personalization,
long-term recall, or router decisions.
