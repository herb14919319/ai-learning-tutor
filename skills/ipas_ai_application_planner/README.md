# iPAS AI 應用規劃師備考 Skill

## Skill 定位

`ipas_ai_application_planner` 是 AI Learning Tutor 內的本地教材 Skill，協助使用者準備 iPAS AI 應用規劃師初級考試。它沿用既有 `SkillManifest`、`SkillRuntime` 與模組式 `answer(question)` 介面，不建立新的 Agent Runtime、Web App、資料庫或外部服務。

## 第一階段支援範圍

- L111 人工智慧概念
- 基礎教材問答
- 章節重點整理
- 10 題單選練習題
- 答案判定與解析
- 教材、章節與段落／表格來源追溯

本階段不支援 L112～L123 的知識問答、完整七章進度、跨章模擬考、向量資料庫、自動更新網路資訊、推薦系統或新 UI。`chapter_index.json` 只替其餘六章建立主講義章節入口，狀態為 `indexed_only`。

## 教材來源與優先順序

原始教材保留在 `knowledge/source/`，解析程序只讀取、不修改 DOCX，也不會把內容傳送到外部 API。

1. `ipas_official_topics.docx`：七大章節主架構（`core_outline`）
2. `ipas_generative_ai.docx`：科目二、新技術、治理與 XAI 補充（`detailed_reference`）
3. `ipas_exam_analysis_114_115.docx`：題型、出題方向與考點參考（`exam_analysis`）

課程講義即使自述依官方評鑑範圍編排，也不在本 Skill 中被描述為官方法規或官方唯一標準。法規與機構資訊可能隨時間改變，本 MVP 不自動連網更新。

`source_manifest.json` 另記錄每份原始檔的位元組大小與 SHA-256，方便確認重新解析前後是否仍是同一份教材。

## 目錄結構

```text
skills/ipas_ai_application_planner/
├── __init__.py
├── skill.py
├── README.md
├── scripts/
│   └── process_sources.py
└── knowledge/
    ├── source/                 # 三份原始 DOCX，只讀保留
    ├── source_pending/         # 未納入 MVP 的既有候選教材
    └── processed/
        ├── source_manifest.json
        ├── chapter_index.json
        ├── l111_knowledge.json
        └── l111_questions.json
```

## 功能與呼叫方式

Tutor router 會依 `skills/registry.py` 的 metadata 將 `iPAS`、`AI 應用規劃師`、`L111`、`HITL` 等明確查詢導向本 Skill。未帶 iPAS／L111 特徵的一般 AI 問題仍由原有 AI Tutor Skill 處理。

模組亦提供可測試的最小函式：

- `query_concept(query)`：查詢 L111 觀念。
- `get_key_points()`：取得 L111 重點。
- `get_random_question()`：取得一題不含答案的單選題。
- `submit_answer(question_id, selected_answer)`：判定答案並回傳解析與來源。
- `get_sources()`：取得來源清單與 L111 章節索引。
- `answer(question)`：既有 Tutor Skill 的文字輸入／文字輸出介面。

文字互動範例：

```text
L111 的 HITL 是什麼？
請整理 L111 重點
請出一題 iPAS 測驗
L111-Q001 答案 A
L111 的教材來源
```

## 如何重新解析教材

解析器只使用 Python 標準函式庫讀取 DOCX 內的 OOXML，不需 OCR 或新增大型依賴。從 repository 根目錄執行：

```powershell
python -X utf8 skills\ipas_ai_application_planner\scripts\process_sources.py
```

解析器會先確認三份指定教材與關鍵章節標記都存在；缺檔、DOCX 損壞或章節驗證失敗時會以非零狀態停止，不會假裝成功，也不會覆寫成空資料。成功後才更新四份 `processed` JSON。

## 如何加入新章節

1. 先在 `chapter_index.json` 的產生邏輯中確認章節代碼、名稱與可靠來源區段。
2. 在 `process_sources.py` 新增該章知識與題目建置函式，保持每個項目都有 `source_references`。
3. 不直接複製考古題長段文字；題目應依教材概念重新編寫，並標示 `single_choice_generated`。
4. 新增該章的查詢、答題、來源與缺檔測試。
5. 由人工審核者把確認過的項目由 `pending_review` 改為團隊約定的核准狀態。

一次只擴充一章；不要直接把七章全量塞入同一批變更。

## 人工審核流程

1. 依 `source_references` 回到原始 DOCX 的指定章節、段落範圍或表格。
2. 確認定義沒有超出教材，白話說明沒有改變原意。
3. 確認題目是新寫練習題，不是官方題目，也沒有直接複製考古題長段文字。
4. 對 `conflict` 或 `requires_review` 項目逐一決定是否保留差異、改寫或補充來源。
5. 法規、日期、機構名稱等時效性內容必須另向最新官方資料查核後才能核准。

目前所有知識點與題目的 `review_status` 都是 `pending_review`。

## 已知限制

- 只支援 L111；其他六章僅有章節索引。
- 使用規則式本地關鍵字比對，不是語意向量檢索。
- DOCX 沒有穩定的內建頁碼，因此追溯以章節、段落索引與表格索引為主，不猜測頁碼。
- 「AI 定義」是由 L111 分類與應用內容整理出的綜合定義，已標記 `requires_review`。
- Strong AI 與 AGI 的關係在主講義與考古分析報告中措辭不同，已保留 `conflict`，未強行合併。
- 法規與機構資訊不會自動更新；本 MVP 不提供最新法規保證。
