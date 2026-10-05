# Phase 6 physical-security review packet

All content below was generated as pending_review. Owner decisions are recorded only in `knowledge/processed/review_decisions.json`; see "L. Review progress" in `PHASE6_PRODUCTION_REPORT.md` for the checked-in state. Payloads below reflect the current files, including the I11-PHYS-004 revision. Source: `iPAS_資訊安全管理概論_PART_I.pdf`, one-based PDF pp. 84–90. Review the original rendered pages alongside the paraphrased observations. The canonical PDF hash is in `source_manifest.json`.

## 1. Canonical visual/transcription checks

- Check p. 85 four-column labels and body: facility access, personnel control, perimeter protection, intrusion detection. This page was legible in bounded rendering, but the image-only source has no machine transcription.
- Check p. 88 fail safe / fail secure fire-state examples and p. 90 “一般” 40%–60% humidity wording. These are high-value exam distinctions.
- No canonical visual verification decision is recorded here.

## 2. Learning Chunks

### I11-PHYS-001 — PDF p. 84

```json
{
  "chunk_id": "I11-PHYS-001",
  "title": "支持系統與實體安全",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      84
    ],
    "source_title": [
      "內部的支持系統"
    ],
    "observations": [
      "投影片說實體環境保護之外，電力、水與空調等日常設施正常運作也是安全條件；並列電力、環境控制、空調、火災四項。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "實體安全也依賴維持機房運作的支持系統。",
    "explanation": "牆與門之外，停電、漏水或空調失效也可能使系統無法服務。",
    "exam_focus": "把電力、環境監測、空調與火災防護歸入支持系統；不能只想到門禁。",
    "related_concepts": [
      "I11-PHYS-002",
      "I11-PHYS-003",
      "I11-PHYS-010"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-002 — PDF p. 84

```json
{
  "chunk_id": "I11-PHYS-002",
  "title": "主要與次要電力來源",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      84
    ],
    "source_title": [
      "內部的支持系統"
    ],
    "observations": [
      "電力項把來源分為主要及次要；主要來源中斷時由次要來源供電，例子為發電機。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "次要電力是主要供電中斷時的替代來源。",
    "explanation": "這是供電連續性的安排；來源舉發電機，但未規定切換時間或容量。",
    "exam_focus": "區分主要與次要來源，不把發電機說成唯一選項。",
    "related_concepts": [
      "I11-PHYS-001"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-003 — PDF p. 84

```json
{
  "chunk_id": "I11-PHYS-003",
  "title": "環境控制與火災防護",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      84
    ],
    "source_title": [
      "內部的支持系統"
    ],
    "observations": [
      "環境控制項要求水、電、瓦斯與空調熟悉緊急開關，環控系統發出通知警訊；火災項提及滅火方式、自動偵測與滅火設備。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "環境控制要能發現異常，也要知道如何處置。",
    "explanation": "警訊、緊急開關及火災設備在來源中分別承擔告警與處置用途。",
    "exam_focus": "告警不等於滅火；緊急開關與自動偵測也不是同一功能。",
    "related_concepts": [
      "I11-PHYS-001",
      "I11-PHYS-010"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-004 — PDF p. 85

```json
{
  "chunk_id": "I11-PHYS-004",
  "title": "周邊安全的四類控制",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "comparison",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      85
    ],
    "source_title": [
      "周邊安全(perimeter security)"
    ],
    "observations": [
      "頁面四欄依序為設施門禁、人員進出控管、周邊保護機制、入侵偵測；下方分別說明監控記錄、辨識驗證、多元防護及偵測改變。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "周邊安全從進出限制延伸到辨識、防護與偵測。",
    "explanation": "四欄是並列的控制面向：第三欄「周邊保護機制」著重避免或拖延非法入侵；第四欄「入侵偵測」著重透過自動感測及早發現入侵。監視系統與感測裝置可同時參與不同防護目的，並非互斥設備。",
    "exam_focus": "不要把入侵偵測誤當作門禁授權，也不要認為只有圍牆即可。",
    "related_concepts": [
      "I11-PHYS-006",
      "I11-PHYS-008",
      "I11-PHYS-009"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-005 — PDF p. 86

```json
{
  "chunk_id": "I11-PHYS-005",
  "title": "安全空間的結構設計",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      86
    ],
    "source_title": [
      "建立實體安全環境"
    ],
    "observations": [
      "安全實體空間須評估各組成項目；天花板與地板需考量承重及防火，牆面需考量防火與堅固，門窗需考量入侵可能性及緊急出口。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "安全空間要按其用途檢查結構與出入口。",
    "explanation": "機房不是只裝門鎖；天花板、地板、牆、門窗各有不同設計條件。",
    "exam_focus": "門的堅固性與緊急出口可用性需同時評估。",
    "related_concepts": [
      "I11-PHYS-006",
      "I11-PHYS-008"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-006 — PDF p. 87

```json
{
  "chunk_id": "I11-PHYS-006",
  "title": "安全區域分級與標示",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      87
    ],
    "source_title": [
      "安全區域設計"
    ],
    "observations": [
      "頁面說按不同安全等級劃分實體區域，常見例子有控管、限制、公開、機敏；區域圖須標示安全要求等級，並舉電腦資訊設備機房與電力機房。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "區域分級使不同空間採用相稱的實體控制。",
    "explanation": "先辨識區域安全要求，再規劃邊界與控制；來源的四個詞是常見分法，不是普遍強制級別。",
    "exam_focus": "公開區與機敏區不應預設同一進出控制。",
    "related_concepts": [
      "I11-PHYS-004",
      "I11-PHYS-005",
      "I11-PHYS-007"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-007 — PDF p. 87

```json
{
  "chunk_id": "I11-PHYS-007",
  "title": "區域偵測與屏障",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      87
    ],
    "source_title": [
      "安全區域設計"
    ],
    "observations": [
      "頁面要求安全區域有適當偵測器；煙霧偵測器置於天花板下風處，通風口加裝鐵網；較高安全等級的區域採較強牆面並確認由樓地板連接至天花板。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "區域設計結合偵測與防穿越的實體屏障。",
    "explanation": "偵測器提醒異常，牆面與通風口處理繞過邊界的可能路徑。",
    "exam_focus": "不要只檢查門，忽略天花板、通風口與牆面連接。",
    "related_concepts": [
      "I11-PHYS-005",
      "I11-PHYS-006"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-008 — PDF p. 88

```json
{
  "chunk_id": "I11-PHYS-008",
  "title": "門的 fail safe 與 fail secure",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "comparison",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      88
    ],
    "source_title": [
      "門窗的安全"
    ],
    "observations": [
      "投影片說門依疏散方向向外順向開啟；fail safe 例子平時上鎖、火災時保持開啟，適用有人員作業的區域；fail secure 例子平時上鎖、火災時保持關閉，適用無人的倉庫區域。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "門的火災狀態須與人員疏散及物品保護需求一起判斷。",
    "explanation": "來源用有人作業區與無人倉庫對照兩種狀態；它未給出所有建築或法規情境的通則。",
    "exam_focus": "兩者平時都上鎖；本頁的考點是火災時開啟或關閉的差別。",
    "related_concepts": [
      "I11-PHYS-005",
      "I11-PHYS-009"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-009 — PDF p. 89

```json
{
  "chunk_id": "I11-PHYS-009",
  "title": "進出口與監視錄影",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      89
    ],
    "source_title": [
      "實體設施的控管"
    ],
    "observations": [
      "頁面列大門、側門、緊急出口、車輛貨物進出等需辨識與控管，留意尾隨；監視錄影可協助動作偵測與身份識別，並需確保監視系統安全及妥善保存錄影資料。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "出入口管制與錄影紀錄要一起規劃。",
    "explanation": "辨識進出者與避免尾隨屬入口控制；錄影可輔助追查，但監視系統及紀錄本身也要保護。",
    "exam_focus": "攝影機不能替代進出辨識；緊急出口也在管制視野內。",
    "related_concepts": [
      "I11-PHYS-004",
      "I11-PHYS-008"
    ],
    "review_status": "pending_review"
  }
}
```

### I11-PHYS-010 — PDF p. 90

```json
{
  "chunk_id": "I11-PHYS-010",
  "title": "空調與通風維護",
  "chapter": "I11 資訊安全管理概論",
  "section": "實體安全：支持系統、周邊、區域與設施",
  "chunk_type": "concept",
  "source_evidence": {
    "source_file": "iPAS_資訊安全管理概論_PART_I.pdf",
    "source_pages": [
      90
    ],
    "source_title": [
      "空調系統"
    ],
    "observations": [
      "頁面要求空調規劃、正壓、開門時氣流往外吹送、濕度一般控制在 40%–60%、換氣與進氣口保護、煙霧自動偵測、獨立電力供應路線及維修保養紀錄。"
    ]
  },
  "teaching_interpretation": {
    "core_concept": "空調是機房可用性與環境保護的一部分。",
    "explanation": "溫濕度、氣流、換氣、電力與維護都需考慮；40%–60% 是本投影片的一般說法，不應當成所有設備的絕對規範。",
    "exam_focus": "空調不只降溫，還涉及正壓、濕度、進氣保護及維護紀錄。",
    "related_concepts": [
      "I11-PHYS-001",
      "I11-PHYS-003"
    ],
    "review_status": "pending_review"
  }
}
```

## 3. Teaching Section

# I11 資訊安全管理概論：實體安全控制

> Review status: `pending_review`。以下是生成教學內容，並非來源逐字稿。來源：`iPAS_資訊安全管理概論_PART_I.pdf`，PDF 第 84–90 頁；對應 `I11-PHYS-001`–`010`。所有原創情境均為教學輔助，須由擁有者審核。

## 1. 概念總覽

實體安全不只守住機房的門。第 84 頁把電力、環境控制、空調與火災防護列為支持系統；第 85–89 頁依序討論周邊、空間、區域、門及出入口；第 90 頁再細化空調維護。可以把它想成「能進來的人與物、空間本身、支撐運作的設施」三個檢查方向。`I11-PHYS-001`、`004`、`005`、`010`

## 2. 白話解釋與概念關係

**支持系統**：主要電力中斷時需有次要電力；環控應能通知異常，操作人員也應熟悉水、電、瓦斯與空調的緊急開關。火災防護另涉及偵測及滅火設備。告警、供電與處置各有用途。`I11-PHYS-001`–`003`，PDF p. 84。

**周邊與區域**：p. 85 的四欄是設施門禁、人員進出控管、周邊保護機制、入侵偵測。p. 87 進一步要求依安全等級劃分區域、標示要求，並考量偵測器、牆面及通風口等邊界。前者是控制面向，後者是把控制落到不同空間。`I11-PHYS-004`、`006`、`007`。

**空間與進出口**：p. 86 要逐項評估天花板、地板、牆、門窗的承重、防火、堅固與緊急出口需求。p. 89 要管制大門、側門、緊急出口及貨物車輛進出，注意尾隨，並保護監視系統及錄影資料。`I11-PHYS-005`、`009`。

**門的兩種火災狀態**：p. 88 的例子中，fail safe 與 fail secure 平時都上鎖；火災時前者保持開啟，例示有人作業區；後者保持關閉，例示無人倉庫。這是該投影片的對照，實際設計仍須依場所要求判斷。`I11-PHYS-008`。

**空調**：p. 90 除溫度與濕度，還提正壓、外吹氣流、換氣、進氣口保護、煙霧偵測、獨立供電及維修紀錄。來源把濕度一般控制範圍寫為 40%–60%；不要將此概括成所有設備的通用規範。`I11-PHYS-010`。

## 3. 原創工程情境（教學輔助，非來源案例）

某棟大樓的 BA／IBMS 機房新增伺服器與網路交換器。工程團隊在出入口辨識與防尾隨之外，檢查備援供電、環境告警、空調進氣口及維修紀錄。這個情境用來串起 p. 84、85、89、90 的控制面向；來源沒有描述這棟大樓，也沒有給設備規格。`I11-PHYS-001`、`002`、`004`、`009`、`010`。

另一個原創情境：有人值守的控制室與無人備品庫的門，火災時的預期狀態可能不同。先確認疏散與保護需求，再讀 p. 88 的兩種例子；不能只按英文名稱猜測。`I11-PHYS-008`。

## 4. 常見誤解與 iPAS 區辨

- 「裝攝影機就等於完成門禁」：p. 85 分開列人員進出控管與入侵偵測，p. 89 也分別說出入口辨識及監視錄影。`I11-PHYS-004`、`009`
- 「區域有門就足夠」：p. 86–87 仍要求檢查牆、天花板、地板、通風口與偵測器。`I11-PHYS-005`–`007`
- 「fail safe 是平時不上鎖」：p. 88 兩種例子都說平時上鎖，差異在火災時狀態。`I11-PHYS-008`
- 「空調只管溫度」：p. 90 還列濕度、氣流、換氣、進氣保護、供電與維護。`I11-PHYS-010`

## 5. 短記憶線索

「供電與環控 → 周邊進出 → 區域結構 → 門的火災狀態 → 空調維護」。這是**生成的記憶輔助**，不是投影片原句。遇到題目先辨認它問的是預防進入、偵測異常、疏散，還是維持設施運作。

## 4. Flashcards

### I11-PHYS-F001

```json
{
  "card_id": "I11-PHYS-F001",
  "front": "實體安全的內部支持系統包含哪些面向？",
  "back": "第 84 頁列電力、環境控制、空調及火災防護。",
  "chunk_ids": [
    "I11-PHYS-001"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F002

```json
{
  "card_id": "I11-PHYS-F002",
  "front": "主要電力中斷時，來源要求什麼？",
  "back": "由次要電力來源供電；投影片舉發電機為例。",
  "chunk_ids": [
    "I11-PHYS-002"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F003

```json
{
  "card_id": "I11-PHYS-F003",
  "front": "環境控制的告警與火災設備有何不同？",
  "back": "環控通知異常；火災防護另考量自動偵測及滅火設備。",
  "chunk_ids": [
    "I11-PHYS-003"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F004

```json
{
  "card_id": "I11-PHYS-F004",
  "front": "第 85 頁周邊安全的四個面向是什麼？",
  "back": "設施門禁、人員進出控管、周邊保護機制、入侵偵測。",
  "chunk_ids": [
    "I11-PHYS-004"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F005

```json
{
  "card_id": "I11-PHYS-F005",
  "front": "機房的天花板與地板應注意什麼？",
  "back": "第 86 頁要求考量承重與防火；不能只檢查門鎖。",
  "chunk_ids": [
    "I11-PHYS-005"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F006

```json
{
  "card_id": "I11-PHYS-F006",
  "front": "安全區域設計為何要分級？",
  "back": "依不同安全要求劃分空間，標示要求並規劃相稱控制。",
  "chunk_ids": [
    "I11-PHYS-006"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F007

```json
{
  "card_id": "I11-PHYS-F007",
  "front": "安全區域除門之外還要檢查哪些穿越路徑？",
  "back": "第 87 頁提牆面連接、通風口及偵測器配置。",
  "chunk_ids": [
    "I11-PHYS-007"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F008

```json
{
  "card_id": "I11-PHYS-F008",
  "front": "第 88 頁 fail safe 與 fail secure 的火災時狀態？",
  "back": "例子中前者保持開啟，後者保持關閉；兩者平時都上鎖。",
  "chunk_ids": [
    "I11-PHYS-008"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F009

```json
{
  "card_id": "I11-PHYS-F009",
  "front": "出入口控管為何不能只靠攝影機？",
  "back": "來源還要求辨識進出、注意尾隨；錄影是輔助且資料須保存。",
  "chunk_ids": [
    "I11-PHYS-009",
    "I11-PHYS-004"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F010

```json
{
  "card_id": "I11-PHYS-F010",
  "front": "空調系統除溫度外還涉及什麼？",
  "back": "濕度、正壓與氣流、換氣、進氣保護、供電及維修紀錄。",
  "chunk_ids": [
    "I11-PHYS-010"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F011

```json
{
  "card_id": "I11-PHYS-F011",
  "front": "來源對濕度的措辭是什麼？",
  "back": "第 90 頁說一般控制在 40%–60%；不應當成所有設備的絕對規範。",
  "chunk_ids": [
    "I11-PHYS-010"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

### I11-PHYS-F012

```json
{
  "card_id": "I11-PHYS-F012",
  "front": "周邊防護與入侵偵測的作用如何區分？",
  "back": "前者以屏障等方式阻擋或延遲侵入；後者感測改變、提早發現事件。",
  "chunk_ids": [
    "I11-PHYS-004",
    "I11-PHYS-007"
  ],
  "content_origin": "generated_teaching",
  "review_status": "pending_review"
}
```

## 5. Quiz Questions (reviewer view: answer and explanation included)

### I11-PHYS-Q001

```json
{
  "question_id": "I11-PHYS-Q001",
  "cognitive_level": "recall",
  "question": "第 84 頁哪一項屬於實體安全的內部支持系統？",
  "options": {
    "A": "次要電力來源",
    "B": "密碼複雜度",
    "C": "資料庫索引",
    "D": "軟體版本控制"
  },
  "correct_answer": "A",
  "explanation": "第 84 頁明列主要與次要電力來源。",
  "chunk_ids": [
    "I11-PHYS-001",
    "I11-PHYS-002"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q002

```json
{
  "question_id": "I11-PHYS-Q002",
  "cognitive_level": "distinction",
  "question": "主要電力中斷時，哪一項最符合來源描述？",
  "options": {
    "A": "等待主要電力自行恢復",
    "B": "由次要電力來源供電",
    "C": "先刪除伺服器資料",
    "D": "只更換門鎖"
  },
  "correct_answer": "B",
  "explanation": "第 84 頁說主要來源中斷時由次要來源供電，並舉發電機。",
  "chunk_ids": [
    "I11-PHYS-002"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q003

```json
{
  "question_id": "I11-PHYS-Q003",
  "cognitive_level": "distinction",
  "question": "哪一組把第 85 頁的周邊控制與其作用正確配對？",
  "options": {
    "A": "入侵偵測—辨識進出身分",
    "B": "人員進出控管—辨識與驗證",
    "C": "周邊保護—只保存錄影",
    "D": "設施門禁—調節濕度"
  },
  "correct_answer": "B",
  "explanation": "人員進出控管欄指出進出人員的辨識與驗證。",
  "chunk_ids": [
    "I11-PHYS-004"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q004

```json
{
  "question_id": "I11-PHYS-Q004",
  "cognitive_level": "scenario",
  "question": "原創情境：機房有門禁，但通風口可直接穿越邊界。應優先對照哪個來源提醒？",
  "options": {
    "A": "第 87 頁通風口加裝鐵網與區域屏障",
    "B": "第 90 頁濕度範圍",
    "C": "第 84 頁發電機",
    "D": "第 88 頁平時上鎖"
  },
  "correct_answer": "A",
  "explanation": "第 87 頁同時談區域邊界、通風口與較高安全等級牆面。",
  "chunk_ids": [
    "I11-PHYS-007"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q005

```json
{
  "question_id": "I11-PHYS-Q005",
  "cognitive_level": "recall",
  "question": "第 87 頁區域規劃圖應標示什麼？",
  "options": {
    "A": "各區域的安全要求等級",
    "B": "所有伺服器密碼",
    "C": "每位員工薪資",
    "D": "所有防火牆規則"
  },
  "correct_answer": "A",
  "explanation": "來源要求區域規劃圖標示各區域安全要求等級。",
  "chunk_ids": [
    "I11-PHYS-006"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q006

```json
{
  "question_id": "I11-PHYS-Q006",
  "cognitive_level": "comparison",
  "question": "依第 88 頁例子，fail safe 與 fail secure 在火災時的差異是什麼？",
  "options": {
    "A": "前者開啟、後者關閉",
    "B": "前者關閉、後者開啟",
    "C": "兩者平時均不上鎖",
    "D": "兩者火災時均開啟"
  },
  "correct_answer": "A",
  "explanation": "投影片例子說前者火災時保持開啟，後者保持關閉；平時兩者均上鎖。",
  "chunk_ids": [
    "I11-PHYS-008"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q007

```json
{
  "question_id": "I11-PHYS-Q007",
  "cognitive_level": "scenario",
  "question": "原創情境：有人值守區的門在火災時必須利於疏散。第 88 頁哪個例子較貼近？",
  "options": {
    "A": "無人倉庫的 fail secure 例子",
    "B": "有人作業區的 fail safe 例子",
    "C": "只安裝攝影機",
    "D": "取消所有進出口辨識"
  },
  "correct_answer": "B",
  "explanation": "來源以有人員作業區說明 fail safe 火災時保持開啟。",
  "chunk_ids": [
    "I11-PHYS-008"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q008

```json
{
  "question_id": "I11-PHYS-Q008",
  "cognitive_level": "distinction",
  "question": "第 89 頁對實體進出口控管的提醒包含哪一項？",
  "options": {
    "A": "僅管正門，不管側門",
    "B": "留意尾隨進出的情況",
    "C": "監視系統不需保護",
    "D": "錄影資料不需保存"
  },
  "correct_answer": "B",
  "explanation": "來源列多種出入口並提醒留意尾隨，監視系統與錄影資料也需保護。",
  "chunk_ids": [
    "I11-PHYS-009"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q009

```json
{
  "question_id": "I11-PHYS-Q009",
  "cognitive_level": "scenario",
  "question": "原創情境：IBMS 機房已有攝影機，卻沒有檢查進出者身分。哪個控制仍缺？",
  "options": {
    "A": "人員進出辨識與驗證",
    "B": "資料庫備份排程",
    "C": "密碼雜湊演算法",
    "D": "軟體授權盤點"
  },
  "correct_answer": "A",
  "explanation": "第 85 頁分列人員進出控管與入侵偵測；第 89 頁要求進出口辨識。",
  "chunk_ids": [
    "I11-PHYS-004",
    "I11-PHYS-009"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q010

```json
{
  "question_id": "I11-PHYS-Q010",
  "cognitive_level": "recall",
  "question": "第 90 頁對空調環境的敘述何者正確？",
  "options": {
    "A": "只需控制溫度",
    "B": "濕度一般控制在 40%–60%",
    "C": "進氣口無須保護",
    "D": "維修紀錄可不保存"
  },
  "correct_answer": "B",
  "explanation": "來源以「一般」措辭列 40%–60%，並要求進氣保護及維修紀錄。",
  "chunk_ids": [
    "I11-PHYS-010"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q011

```json
{
  "question_id": "I11-PHYS-Q011",
  "cognitive_level": "distinction",
  "question": "哪一項是第 86 頁安全空間設計而非第 90 頁空調維護的考量？",
  "options": {
    "A": "天花板與地板承重及防火",
    "B": "空調獨立供電",
    "C": "濕度一般範圍",
    "D": "維修保養紀錄"
  },
  "correct_answer": "A",
  "explanation": "第 86 頁對結構組成項目要求承重、防火等評估。",
  "chunk_ids": [
    "I11-PHYS-005",
    "I11-PHYS-010"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

### I11-PHYS-Q012

```json
{
  "question_id": "I11-PHYS-Q012",
  "cognitive_level": "scenario",
  "question": "原創情境：伺服器室的環控只記錄溫度，沒有異常通知或緊急關閉資訊。哪個來源點最直接？",
  "options": {
    "A": "第 84 頁環境控制與緊急開關",
    "B": "第 87 頁區域分級名稱",
    "C": "第 88 頁門的疏散方向",
    "D": "第 89 頁車輛貨物進出"
  },
  "correct_answer": "A",
  "explanation": "第 84 頁提水、電、瓦斯、空調緊急開關與環控通知警訊。",
  "chunk_ids": [
    "I11-PHYS-003"
  ],
  "question_type": "single_choice_generated",
  "review_status": "pending_review"
}
```

## Review use

Inspect source pages and each exact payload above, then use the existing `review.py show`/`decide` commands only after the owner supplies decisions. Cards and questions may be reviewed in bounded batches; record each resulting asset decision explicitly.
