# Cybersecurity source inventory — Phase 0

Inventory date: 2026-10-01. Page numbers below are **one-based PDF page numbers**; the four teaching PDFs appear to be slide exports, so a PDF page is the available slide locator. There are **no PPT or PPTX files** in `knowledge/source/` today. The six PDFs total **595 pages**. All files remain canonical in `knowledge/source/`.

## Files

| Source file (under `knowledge/source/`) | Pages | Role and detected structure | Extraction |
| --- | ---: | --- | --- |
| `iPAS_資訊安全管理概論_PART_I.pdf` | 114 | Teaching deck: management concepts, CIA, management systems/ISO 27001, ethics/privacy, asset classification, physical security, risk management; pp. 1–5 front matter, p. 6 section divider, p. 114 Q&A | 0 pages with extractable text; visual review required |
| `iPAS_資訊安全管理概論_PART_II.pdf` | 109 | Teaching deck: access control and authentication, cryptography/key management, incident response, continuity/recovery; p. 1 section divider, p. 60 Q&A divider, p. 109 Q&A | 0 pages with extractable text; visual review required |
| `iPAS_資訊安全技術概論_PART_I.pdf` | 103 | Teaching deck: network/communications security, network and application attacks, defenses, wireless and transport security, secure development and outsourcing; pp. 1–4 front matter, p. 5 section divider, p. 103 Q&A | 0 pages with extractable text; visual review required |
| `iPAS_資訊安全技術概論_PART_II.pdf` | 165 | Teaching deck: malware, analysis/defense, vulnerability assessment and related technical controls; p. 1 and p. 2 section/title slides, p. 40 Trojan/backdoor divider | 0 pages with extractable text; visual review required |
| `iPAS_資訊安全工程師_樣題&考古題_資訊安全管理概論.pdf` | 54 | Exam reference, I11: sample pp. 1–9; 113 first sitting pp. 10–23; 113 second sitting pp. 24–39; 114 first sitting pp. 40–54 | Text extractable; question pages often contain several questions |
| `iPAS_資訊安全工程師_樣題&考古題_資訊安全技術概論.pdf` | 50 | Exam reference, I12: sample pp. 1–9; 113 first sitting pp. 10–21; 113 second sitting pp. 22–35; 114 first sitting pp. 36–50 | Text extractable; question pages often contain several questions |

The four teaching decks' empty text extraction is a significant ingestion constraint. PDF objects alone do not classify a page reliably as text, diagram, or table. The observations below are based on rendered-page review, and the ranges are **likely boundaries, not a completed slide-by-slide OCR index**. In Phase 1, render and transcribe the selected topic pages, then verify titles and locators by eye before processing.

SHA-256 fingerprints of the current canonical files (in table order):

| Source suffix | SHA-256 |
| --- | --- |
| `資訊安全管理概論_PART_I.pdf` | `5088642E71AE02D30E6C89CC80DE17F94240B117B819CD810A05AB9CEC8A7872` |
| `資訊安全管理概論_PART_II.pdf` | `38E0EFD714DA6416FA720769DB2249A0C28FB8D12F2BB61177E675A39663172B` |
| `資訊安全技術概論_PART_I.pdf` | `7C9BE2A8CD81C70A120A83190F04DBF04ABB927312091EFB7369553DE5857111` |
| `資訊安全技術概論_PART_II.pdf` | `DF1C418C8DA9B15B364264240F6767E7DEF35786126630247CED7EC8FC991E91` |
| `樣題&考古題_資訊安全管理概論.pdf` | `FD48952B5B029FF557A5E750ED417C86A2DEF2814457B5E19D16A730A600F315` |
| `樣題&考古題_資訊安全技術概論.pdf` | `2D642FCEC57C6DBBBD6C03F8C96CD33C4F6FF637B0C2859455F5F77E5E8691CC` |

## Detected titles and likely topic boundaries

| Deck | Observed page/title landmarks | Likely topic boundary |
| --- | --- | --- |
| Management I | p. 5 `資訊安全管理概論考題方向`; p. 6 `資訊安全管理概念`; p. 8 `建立資訊安全的危機意識`; pp. 13, 15–17 CIA; p. 20 management-system scope; p. 30 `ISO 27001`; p. 40 `資訊倫理 - PAPA`; p. 50 personal-data rights; p. 60 patents; p. 70 audit purpose; p. 80 asset value classification; p. 90 physical/air-conditioning controls; p. 100 risk management process | Intro/security goals around pp. 6–17; governance/ISMS around pp. 18–39; ethics and privacy around pp. 40–59; audit and assets around pp. 60–89; physical security/risk around pp. 90–113. Verify exact transitions. |
| Management II | p. 1 `存取控制、加解密與金鑰管理` divider; pp. 2–10 access-control concepts/models; p. 15 authentication factors; p. 20 OTP; p. 30 access-control operations table; p. 40 password practice; p. 50 asymmetric cryptography; p. 60 Q&A; p. 70 incident plan; p. 80 containment/eradication/recovery; p. 90 business-continuity lifecycle; p. 100 recovery strategy | Access control/authentication approximately pp. 1–40; cryptography/key management approximately pp. 41–59; incident response and continuity approximately pp. 61–108. Verify exact transitions. |
| Technology I | p. 4 exam-topic directions; p. 5 `網路與通訊安全` divider; p. 6 network security; p. 8 OSI; p. 10 OSI layers; p. 15 port scanning; p. 20 ARP spoofing; p. 30 DDoS; p. 40 XSS; p. 50 intrusion detection; p. 60 spam filtering; p. 70 wireless security; p. 80 SSL question; p. 90 secure-development lifecycle; p. 100 outsourcing-management points | Network models/reconnaissance around pp. 5–18; network attacks around pp. 19–35; application attacks around pp. 36–45; detection/defense around pp. 46–69; wireless/transport around pp. 70–85; secure development/outsourcing around pp. 86–102. Verify exact transitions. |
| Technology II | p. 1 `資安維運技術` divider; p. 2 malware analysis/detection/cleaning/protection title; p. 3 malware introduction; p. 5 history; p. 10 evolution; p. 20 spread; p. 30 worm; p. 40 Trojan/backdoor divider; p. 50 keylogger; p. 60 ransomware media slide; p. 70 botnet; p. 80 dynamic analysis; p. 100 vulnerability assessment; p. 165 data-protection law | Malware foundations approximately pp. 2–39; types/examples approximately pp. 40–75; analysis/defense and vulnerability assessment after p. 75; later data protection material near end. More review needed before chapter assignments. |

The exam PDFs are **exam references**, not teaching chapters. Their sitting boundaries are exact from extractable page headers. They can inform exam points and original practice-question design; do not copy whole past-paper items into generated quizzes.

## Slide treatment flags from rendered samples

| Treatment | Examples (PDF page) | Reason |
| --- | --- | --- |
| Structural metadata only | Management I 1–6 and 114; Management II 1, 60, 109; Technology I 1–5 and 103; Technology II 1–2 and 40 | Cover, syllabus/table of contents, section divider, or Q&A divider; usually no standalone concept chunk. |
| Text-heavy, may split | Management I 11–13 and 16; Management II 2–3, 8, 20, 70, 80; Technology I 6, 8, 40, 90, 100; Technology II 6, 20, 80, 100, 165 | Multiple definitions, controls, steps, or legal points can require more than one semantic unit per page. |
| Diagram/table/visual-heavy | Management I 2–3, 15, 20, 70, 80, 100; Management II 4–6, 15, 30, 40, 50, 90; Technology I 2–3, 10, 15, 20, 30, 50; Technology II 3, 5, 8, 40, 60, 70 | Preserve page image and describe the visual only after review; extracted text is unavailable in the teaching decks. |
| Likely merge with adjacent pages | Management I 13 + 15–17 (CIA definitions, visual, control map); Management II 2–6 (access-control introduction and model); Technology I 8–10 (OSI model/layers); Technology II 2–6 (malware introduction/history/traits) | One concept spans multiple slides or one page supplies only the visual/example for nearby explanation. |
| Likely split within a page | Management I 13 (CIA's three distinct goals), 17 (controls per goal); Management II 8 (preventive/detective/corrective and further control functions), 15 (three factor categories); Technology I 40 (XSS mechanism and defenses); Technology II 20 (different propagation methods), 100 (assessment terms/process) | Several independently teachable ideas share a single slide. |
| Exam questions | Both exam PDFs, all pages | Chunk by question and sitting, with page locator and question number; a page is never the quiz-item boundary. |

These flags are review candidates, not automated classifications for every slide. Page titles and chapter boundaries elsewhere in the four image-only decks need OCR/manual verification.

## Provisional chapter map

1. **I11 / Management:** security foundations and CIA (Management I, early slides).
2. **I11 / Management:** governance, ISMS, ISO 27001, ethics and privacy (Management I, middle slides).
3. **I11 / Management:** audit, assets, physical security, and risk (Management I, later slides).
4. **I11 / Management:** access control and authentication (Management II, early slides).
5. **I11 / Management:** cryptography and key management (Management II, middle slides).
6. **I11 / Management:** incident response and business continuity (Management II, later slides).
7. **I12 / Technology:** network models, reconnaissance, and network attacks (Technology I, early/middle slides).
8. **I12 / Technology:** application attacks, defenses, wireless/transport security, and secure development (Technology I, middle/later slides).
9. **I12 / Technology:** malware types, analysis, and defense (Technology II, early/middle slides).
10. **I12 / Technology:** vulnerability assessment and remaining operations/data-protection topics (Technology II, later slides; verify scope).

These are planning groups, **not** the Phase 1 runtime `chapter_index.json` or finalized course chapter IDs. The Phase 1 index contains only the CIA slice. The two exam-reference PDFs attach by I11/I12 topic and sitting, not as chapters.

## Semantic chunking and traceability for Phase 1

- Use a slide/page as a **source boundary**, then make reviewed units by concept. Candidate kinds: `definition`, `concept`, `comparison`, `process`, `visual`, `exam_point`, `example`. These are planning labels; do not lock a schema yet.
- A chunk can cite one page, several adjacent pages, or one part of a page. Store each cited **canonical source filename**, one-based **PDF page number**, **chapter/section**, and the **slide title** when visible. Also record a source hash in the ingestion manifest so a replacement file cannot silently inherit old citations.
- Keep source quotations/transcriptions separate from generated explanation. A card or quiz explanation should point through its chunk to the original PDF page. If a diagram is essential, keep the original page locator and reviewed visual description; do not substitute a generated diagram for source evidence.
- Mark OCR/transcription uncertainty and human-review status. PDF slide number and a printed slide number may differ; use PDF page number as the stable locator and record printed numbering separately if present.
- The existing `knowledge/processed/chapter_index.json` pattern can be reused once there is reviewed content. Indexes should point to reviewed processed files, while source references point back to `knowledge/source/`.

## Smallest Phase 1 vertical slice

**Phase 1 review completed:** Management I, pp. 13, 15–17 contain CIA goals. Page 13 is titled `資訊安全的目標` and defines the three goals; page 15 is titled `資訊安全的三個目標` and uses three parallel coloured blocks; page 16 repeats that title and expands the definitions, including intentional alteration, noise, and service interruption; page 17 is titled `保護資訊 C.I.A. 不同的技術與方法` and maps control methods to each goal. Page 14, `安全模型 (security model)`, is a related policy/model bridge but was not included in the CIA chunk evidence. The resulting four chunks, six cards, and six original questions are described in `README.md`. Full-course boundaries above remain provisional.

**Phase 2 review completed:** Management I, pp. 92–93 (`風險的定義`) and p. 95 (`認識風險管理`) support a compact threat–vulnerability–risk relationship group. Page 92 has the causal diagram and separates impact from likelihood; page 93 adds the broader ISO 31000:2018 organizational-objective framing; page 95 restates the relation and uses a disease analogy. Page 94 (`認識風險管理`) was context only. Five semantic chunks and their typed relationships are documented in `SCHEMA_STRESS_TEST.md` and `README.md`. The later risk-assessment workflow remains outside this slice.

**Phase 3 review completed:** Management I, p. 103 (`風險管理的流程 - 風險評鑑階段`) explains the assessment purpose and notes iteration; p. 105 (`風險管理的流程 - 風險評鑑階段詳細風險評鑑`) explicitly orders 風險識別 → 風險分析 → 風險評估 with arrows and step descriptions. Page 104 was context only. Four chunks (overview plus three steps) use only those two canonical pages. The broader management lifecycle remains outside this process slice; details are in `PROCESS_SCHEMA_STRESS_TEST.md`.

**Phase 4 pilot:** Management I pp. 77–80 contain asset categories, collection/management, a sample asset register and an A–D asset-value matrix. Page 76 is the divider; p. 81 starts physical security. Seven chunks use pp. 77–80 only. The comparison dimensions and v0.3 limitation are documented in `COMPARISON_SCHEMA_STRESS_TEST.md`; generated assets remain pending review under `REVIEW_GATE.md`.

**Phase 6 controlled production pilot:** Management I pp. 84–90 form a bounded physical-security controls sequence. Visible titles in order: `內部的支持系統`, `周邊安全(perimeter security)`, `建立實體安全環境`, `安全區域設計`, `門窗的安全`, `實體設施的控管`, `空調系統`. Page 83 provides preceding planning context and p. 91 starts emergency procedures; neither is generated into this slice. These seven pages do not overlap the CIA, risk, assessment, or asset source pages. The image-only pages were rendered and inspected individually. Ten new chunks and their dependent teaching, cards, and questions use frozen v0.4 and remain pending review. See `PHASE6_REVIEW_PACKET.md` for the exact review order and content.
