# iPAS 淨零碳規劃師 Skill

## Skill 定位

`ipas_net_zero_planner` 是 AI Learning Tutor 內的本地教材 Skill，協助使用者依章準備 iPAS 淨零碳規劃師課程。實作比照 `ipas_ai_application_planner` 的模組入口、公開函式與本地資料載入方式，不建立新的 Runtime、Router、Core、資料庫、後端服務或外部依賴。

## 課程內容

- 第一章：國內外氣候變遷治理與因應
- 第二章：聯合國氣候變遷大會與 COP
- 第三章：國際重要倡議內容
- 第四章：國際碳稅關貿政策
- 第五章：台灣 2050 淨零路徑
- 第六章：碳資產交易管理架構導論
- 第七章：ISO 14068-1 碳中和標準
- 第八章：ISO 14064 組織型溫室氣體盤查

每章正文只從 `knowledge/processed/ch01～ch08*.md` 載入；圖卡依章從 `cards/chXX/` 自動依檔名順序載入。`knowledge/source/` 的 PDF 僅保留為原始資料，不由 Skill Runtime 讀取。

## 目錄結構

```text
skills/ipas_net_zero_planner/
├── __init__.py
├── skill.py
├── README.md
├── scripts/
│   └── process_sources.py
├── cards/
│   └── ch01/ ... ch08/
└── knowledge/
    ├── source/
    └── processed/
        ├── ch01_*.md ... ch08_*.md
        ├── chapter_index.json
        └── source_manifest.json
```

## 公開介面

沿用既有 Skill 的公開介面：

- `query_concept(query)`：搜尋八章教材並回傳最相關內容。
- `get_key_points()`：回傳各章標題與二級標題重點。
- `get_random_question()`：從章節摘要建立單選複習題。
- `get_questions()`：回傳八章的公開題目資料，不包含答案與完整解析。
- `submit_answer(question_id, selected_answer)`：批改複習題並附教材來源。
- `get_sources()`：列出八份 processed Markdown 教材。
- `answer(question)`：提供 Tutor Runtime 相容的文字入口。

章節式課程另提供：

- `get_course_info()`：淨零碳課程首頁標題、說明與數量資訊。
- `get_chapters()`：首頁／章節列表資料。
- `get_chapter(chapter)`：章節 Markdown、圖卡與上一章／下一章導覽。
- `search(query)`：跨章搜尋並回傳命中摘要。

## 更新索引

Markdown 或圖卡更新後，可重建供檢查與前端消費的索引：

```powershell
python -X utf8 skills\ipas_net_zero_planner\scripts\process_sources.py
```

索引程式只讀取 `knowledge/processed/` 與 `cards/`，不解析原始 PDF。
