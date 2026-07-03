# AI Learning Tutor Deployment Checklist

這份文件整理 AI Learning Tutor 上線前後的檢查項目。目標是協助部署與排錯，不變更主要程式邏輯、router、OpenAI API 呼叫、LINE webhook 或 skill runtime。

## 1. 本機啟動流程

1. 建立並啟用 Python virtual environment。

   macOS / Linux:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   Windows PowerShell:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. 在專案根目錄建立 `.env`，可參考 `.env.example`。

   ```env
   OPENAI_API_KEY=your_openai_api_key
   LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
   LINE_CHANNEL_SECRET=your_line_channel_secret
   OPENAI_MODEL=gpt-4.1-mini
   PORT=8080
   PUBLIC_BASE_URL=http://localhost:8080
   ```

3. 啟動 Flask app。

   ```bash
   python main.py
   ```

4. 若要用接近正式環境的方式啟動，可使用 Gunicorn。

   ```bash
   gunicorn --bind :8080 --workers 1 --threads 8 --timeout 120 main:app
   ```

5. 本機基本確認。

   ```bash
   curl http://localhost:8080/
   curl -X POST http://localhost:8080/web-chat \
     -H "Content-Type: application/json" \
     -d "{\"message\":\"RAG 是什麼？\",\"user_id\":\"local-smoke\"}"
   ```

## 2. Render 部署環境變數

Render Web Service 建議設定：

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 120 main:app`
- Runtime: Python
- Instance type: 依預算與流量選擇；免費或低階方案需預期冷啟動。

必要環境變數：

| 變數 | 用途 | 備註 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 呼叫 OpenAI Responses API | 缺少時 AI 回答流程無法正常產生模型回覆 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE reply / push message | Web chat 不依賴它，但 LINE webhook 需要 |
| `LINE_CHANNEL_SECRET` | 驗證 LINE webhook signature | 與 LINE Developers Console 的 Channel secret 必須一致 |
| `PUBLIC_BASE_URL` | 產生公開 assets URL | 建議設為 Render 服務網址，例如 `https://your-service.onrender.com` |

建議或選用環境變數：

| 變數 | 預設 | 用途 |
| --- | --- | --- |
| `OPENAI_MODEL` | `gpt-4.1-mini` | 指定 OpenAI model |
| `PORT` | Render 自動提供 | 本機預設 `8080`；Render 通常不要手動覆蓋 |
| `AI_REPLY_TIMEOUT_SECONDS` | `45` | LINE 非同步 AI 回答 timeout |
| `BACKGROUND_WORKERS` | `4` | 背景 executor worker 數 |
| `PROCESSED_EVENT_TTL_SECONDS` | `600` | LINE webhook 重複事件防護 TTL |
| `AI_TUTOR_API_KEY` | 空字串 | `/api/tutor/ask` 若有外部呼叫可使用 |
| `MESSENGER_ENABLED` | `false` | Facebook Messenger webhook 開關 |
| `MESSENGER_VERIFY_TOKEN` | 空字串 | Messenger webhook verify token |

部署後請確認 Render logs 中沒有環境變數缺漏、import error 或 worker boot failure。

## 3. LINE Webhook 設定檢查

LINE Developers Console 檢查項目：

- Messaging API channel 已建立並啟用。
- `LINE_CHANNEL_ACCESS_TOKEN` 使用 Messaging API 頁面的 Channel access token。
- `LINE_CHANNEL_SECRET` 使用 Basic settings 頁面的 Channel secret。
- Webhook URL 設為：

  ```text
  https://your-service.onrender.com/callback
  ```

- `Use webhook` 已開啟。
- Auto-reply messages 視需求關閉，避免 LINE 官方自動回覆與 bot 回覆重複。
- 使用 LINE Developers Console 的 Verify 按鈕測試 webhook。
- 若 Rich Menu 圖片或 assets 需要公開讀取，確認 `PUBLIC_BASE_URL` 是可由 LINE 存取的 HTTPS URL。
- Render logs 中若出現 `Invalid LINE signature`，通常是 `LINE_CHANNEL_SECRET` 不一致、Webhook URL 指向錯服務，或請求不是 LINE 官方送出。

## 4. `/healthz` 與 `/web-chat` 測試方式

目前程式碼沒有定義 `/healthz` route。若 Render 或外部監控健康檢查設定為 `/healthz`，目前會得到 404。現階段可以先用 `/` 作為 HTTP availability smoke test，或在未來另行新增 `/healthz` route 後再切換監控設定。

首頁 availability：

```bash
curl -i https://your-service.onrender.com/
```

預期：

- HTTP status 為 `200`
- HTML 內容包含 `AI 學習助教`

Web chat 成功案例：

```bash
curl -i -X POST https://your-service.onrender.com/web-chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"RAG 是什麼？\",\"user_id\":\"render-smoke\"}"
```

預期：

- HTTP status 為 `200`
- JSON 內容包含 `reply`
- Render logs 沒有 OpenAI API exception

Web chat 空輸入案例：

```bash
curl -i -X POST https://your-service.onrender.com/web-chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"   \"}"
```

預期：

- HTTP status 為 `400`
- JSON 內容包含友善錯誤訊息
- 不應呼叫 AI 回答流程

LINE webhook 基本連線測試應使用 LINE Developers Console 的 Verify；不要直接用瀏覽器 GET `/callback`，因為正式 webhook 是 `POST /callback` 且需要 LINE signature。

## 5. 常見錯誤排查

### 冷啟動

現象：

- Render 免費或低階方案閒置後第一次請求較慢。
- LINE 使用者先收到處理中訊息，最終回答延遲。

檢查：

- Render logs 是否顯示 service 正在啟動或 worker boot。
- 首次 `curl /` 是否明顯慢，第二次是否恢復正常。

處理：

- 接受冷啟動延遲，或升級 Render instance。
- 對外說明第一次喚醒可能需要等待。
- 若使用監控 ping，確認不違反平台方案限制。

### 環境變數缺漏

現象：

- Web chat 回覆 fallback。
- LINE Verify 失敗或 webhook 收到 400。
- Logs 出現 OpenAI、LINE authentication 或 signature 相關錯誤。

檢查：

- Render Environment 是否有 `OPENAI_API_KEY`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`。
- `PUBLIC_BASE_URL` 是否為正式 HTTPS URL，且沒有尾端多餘路徑。
- 修改環境變數後是否已 redeploy / restart。

處理：

- 補齊環境變數並重新部署。
- 不要把 secret 寫入 repo 或文件。

### API timeout

現象：

- Logs 出現 `AI Tutor response timed out after ... seconds`。
- LINE 最終收到 timeout fallback。
- Web chat 等待較久後收到 fallback 或前端錯誤訊息。

檢查：

- OpenAI API 狀態、模型延遲與輸入問題長度。
- Render instance CPU / memory 是否不足。
- `AI_REPLY_TIMEOUT_SECONDS` 是否過短。

處理：

- 簡化測試問題確認基本路徑可用。
- 必要時調整 `AI_REPLY_TIMEOUT_SECONDS`。
- 若常態超時，評估升級 instance 或檢查 skill runtime 查詢耗時。

### LINE push / reply 失敗

現象：

- Logs 出現 `LINE reply API failed`、`LINE push API failed` 或 `LINE event has no push recipient id`。
- 使用者只收到處理中訊息，沒有最終答案。

檢查：

- `LINE_CHANNEL_ACCESS_TOKEN` 是否正確且未過期。
- Bot 是否有權限 push message；群組或聊天室情境是否能取得 recipient id。
- 回覆內容是否過長；程式會截斷 LINE 單則訊息，但仍需檢查 LINE API response。
- Webhook 是否重複送事件；logs 可能出現 duplicate event skip。

處理：

- 重新產生 Channel access token 並更新 Render env。
- 確認 bot 已加入聊天室且使用者沒有封鎖 bot。
- 若只在 Rich Menu 圖片失敗，檢查 `PUBLIC_BASE_URL` 與 `/assets/<filename>` 是否可公開存取。

## 6. 上線前 Smoke Test Checklist

- [ ] Render 最新部署成功，service 狀態為 live。
- [ ] Render logs 沒有 import error、worker boot failure 或 secret 缺漏。
- [ ] `GET /` 回傳 `200`，首頁可看到 `AI 學習助教`。
- [ ] `POST /web-chat` 一般問題回傳 `200` 與 JSON `reply`。
- [ ] `POST /web-chat` 空輸入回傳 `400`，且不觸發 AI 呼叫。
- [ ] LINE Developers Console Verify webhook 成功。
- [ ] LINE 實際傳文字訊息後，先收到處理中訊息，稍後收到助教回答。
- [ ] LINE Rich Menu 固定指令可回覆，圖片 assets 可公開讀取。
- [ ] Render `PUBLIC_BASE_URL` 指向目前正式服務網址。
- [ ] 以一題簡單 AI 概念題測試 OpenAI path，例如 `RAG 是什麼？`。
- [ ] 若有外部 agent 使用 `/api/tutor/ask` 或 `/api/agent/ask`，完成一筆測試呼叫。
- [ ] 已記錄目前部署版本、commit SHA 或 Render deploy id。

## 7. 回滾方式

Render 回滾建議流程：

1. 到 Render Dashboard 開啟該 Web Service。
2. 進入 Deploys，找到上一個已知可用的 successful deploy。
3. 使用 Render 的 redeploy / rollback 功能回到該版本。
4. 確認環境變數沒有被新部署改壞；必要時先修正 env 再 redeploy。
5. 執行 smoke test：

   ```bash
   curl -i https://your-service.onrender.com/
   curl -i -X POST https://your-service.onrender.com/web-chat \
     -H "Content-Type: application/json" \
     -d "{\"message\":\"RAG 是什麼？\",\"user_id\":\"rollback-smoke\"}"
   ```

6. 在 LINE Developers Console Verify webhook，並用實際 LINE 帳號傳一則測試訊息。
7. 若問題來自環境變數或平台設定，不需要 git revert；修正 Render 設定並 redeploy 即可。
8. 若問題來自程式碼變更，使用上一個穩定 commit 建立 hotfix / revert commit，再部署。

回滾後要保留：

- 失敗 deploy id、時間與 commit SHA。
- Render logs 中第一個明確錯誤。
- smoke test 結果。
- 是否影響 Web Chat、LINE webhook、Rich Menu 或外部 API。
