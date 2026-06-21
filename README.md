# AI Learning 助教 LINE Bot MVP

這是一個可部署到 Google Cloud Run 的 Python Flask LINE Bot MVP。

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
```

`OPENAI_MODEL` 可省略，預設使用 `gpt-4.1-mini`。

## 本機 .env

本機開發時，請在專案根目錄建立 `.env`：

```env
OPENAI_API_KEY=你的 OpenAI API Key
LINE_CHANNEL_ACCESS_TOKEN=你的 LINE Channel Access Token
LINE_CHANNEL_SECRET=你的 LINE Channel Secret
OPENAI_MODEL=gpt-4.1-mini
PORT=8080
```

`main.py` 啟動時會透過 `python-dotenv` 自動載入 `.env`。如果同一個變數已經存在於系統環境變數中，系統環境變數會保留原值，不會被 `.env` 覆蓋。這讓本機 `.env` 與 Cloud Run 的環境變數設定可以相容。

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

## Cloud Run 部署

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
4. 將 Webhook URL 設為 Cloud Run URL 加上 `/callback`。
5. 啟用 `Use webhook`。
6. 關閉或依需求調整 LINE 官方的 Auto-reply messages，避免與 Bot 回覆重複。
7. 使用 LINE Developers Console 的 Verify 按鈕測試 webhook。

## 使用方式

傳送 `/help` 可取得使用說明。

一般文字訊息會交由 AI Learning 助教回答。第一版只處理文字訊息；圖片、貼圖、語音等訊息會被忽略。

## 免責聲明

本服務為 AI 學習工具，非任何教師、學校或教育機構官方帳號。

本服務可依據學習助教的教學風格/脈絡協助解釋 AI 相關概念，但不宣稱為李宏毅教授、台大或任何教育機構官方服務，也不宣稱取得官方授權。
