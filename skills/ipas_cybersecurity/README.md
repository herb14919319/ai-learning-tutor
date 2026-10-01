# iPAS 資訊安全工程師初級 — four bounded validation slices

This skill is a peer of `ipas_ai_application_planner` and `ipas_net_zero_planner`. Phase 1 established CIA as parallel definitions; Phase 2 added a threat–vulnerability–risk relationship; Phase 3 added an ordered three-step risk-assessment process. Phase 4 pilots an asset-value comparison matrix and local review ledger. All four use the repository's skill discovery, module `answer(question)` interface, and Flask Web app. No new runtime, router, database, workflow engine, or standalone app was added.

## Source of truth and scope

- Canonical source: `knowledge/source/iPAS_資訊安全管理概論_PART_I.pdf`. CIA uses **one-based PDF pages 13, 15, 16, 17**; asset classification uses **pages 77–80**; risk concepts use **pages 92, 93, 95**; risk assessment uses **pages 103, 105**. Pages 14 and 94 were reviewed for context but contribute no chunks.
- `knowledge/processed/source_manifest.json` records the source filename, SHA-256, and pages used. The loader rejects a changed PDF hash until citations are reviewed.
- `knowledge/source_pending/` is reserved for candidate material. The other five PDFs remain untouched and unprocessed.
- `SOURCE_INVENTORY.md` records the wider Phase 0 inventory. `SCHEMA_STRESS_TEST.md` and `PROCESS_SCHEMA_STRESS_TEST.md` record the source-specific trials before each additive schema change. No course-wide chapter map is activated here.

## Learning Chunk v0.1

`knowledge/processed/learning_chunk_schema_v0_1.json` declares the minimum fields, and `cia_chunks.json` contains four semantic units: overview, confidentiality, integrity, and availability. A chunk is **not** a PDF page. The overview spans pages 13, 15, and 16; each goal combines definitions and the control map from pages 13, 16, and 17.

`learning_chunk_schema_v0_2.json` keeps every v0.1 required field and adds one **optional** top-level `relationships` list. An entry has `predicate` and `target_chunk_id`. Page 92's explicit diagram justifies the first predicates: `exploits`, `belongs_to`, `contributes_to`. The loader verifies targets exist and rejects self-links. This is lightweight metadata, not a graph subsystem. Existing CIA chunks remain v0.1 files without migration.

`learning_chunk_schema_v0_3.json` adds **only** `precedes` to that predicate list. Page 105 explicitly orders risk identification, analysis, and evaluation. The loader checks that `precedes` forms one acyclic, unbranched chain across this slice's process chunks, in their recorded order, and cannot cross slices. Page 103 describes assessment as iterative; the chain represents one pass, not a claim that the wider management lifecycle never repeats. CIA v0.1 and Risk v0.2 chunk files load unchanged.

`learning_chunk_schema_v0_4.json` adds an optional, source-backed comparison matrix within `source_evidence`. Page 80 compares A–D asset-value levels on scope, business damage condition and potential impact. The loader checks member/dimension/value completeness and source-page locators; the image-only PDF still requires visual human verification. `COMPARISON_SCHEMA_STRESS_TEST.md` records the v0.3 attempt and exact limitation. Earlier slices load without migration.

Each chunk has `chunk_id`, `title`, `chapter`, `section`, and `chunk_type`, then two separate objects:

- `source_evidence`: canonical filename, PDF pages, visible slide title(s), and reviewed observations of what the slides say/show.
- `teaching_interpretation`: generated core concept, plain-language explanation, exam focus, and related chunk IDs.

The source PDF is never rewritten. Source observations are paraphrases for indexing; the original page remains the authority. Engineering examples and memory cues are explicitly generated teaching aids. New risk chunk interpretations, cards, teaching prose and questions are marked `pending_review`.

## Derived learning content

- `knowledge/processed/cia_teaching.md`: one concise teaching section, with architecture, plain-language distinctions, generated engineering scenarios, exam traps, and source/chunk references.
- `cards/cia_flashcards.json`: six text flashcards, each with `chunk_ids` and `content_origin=generated_teaching`.
- `knowledge/processed/cia_questions.json`: six original single-choice questions across recall, distinction, and short scenarios. These are **not** copied past-exam items. Each has `chunk_ids`, an answer and explanation, and `pending_review` status. Browser question payloads omit answers and explanations; grading stays on the server.
- `knowledge/processed/chapter_index.json`: a slice index, not a claim that the wider I11 course is complete.

Phase 2 added `risk_chunks.json` (five chunks), `risk_teaching.md` (one short teaching section), `cards/risk_flashcards.json` (six text cards), and `risk_questions.json` (six original questions). The risk material distinguishes the page 92/95 simplified security relation from page 93's broader ISO 31000 framing. No past-exam questions were imported.

Phase 3 adds `assessment_chunks.json` (overview and three independently cited steps), `assessment_teaching.md`, `cards/assessment_flashcards.json` (six cards), and `assessment_questions.json` (six original questions). The index now has exactly three **slice** entries, still not a complete chapter map. All new generated teaching and assessment assets are `pending_review`.

Phase 4 adds `asset_chunks.json` (seven chunks), `asset_teaching.md` (one concise section), `cards/asset_flashcards.json` (ten cards), and `asset_questions.json` (ten original questions). The index has four bounded slice entries, not a complete chapter. All new content starts `pending_review`. `REVIEW_GATE.md` documents the local accept/revise/reject command and runtime policy. Pending content remains visible with its status; revision-required and rejected content is hidden, including dependent cards/questions. Review decisions apply only to generated payload hashes, never canonical PDF evidence.

## Consumption

- Tutor Runtime: `skill.json` activates `skills.ipas_cybersecurity`. Explicit cybersecurity/CIA queries route through existing skill discovery to `answer(question)`. Public functions include `get_chapter`, `get_flashcards`, `get_questions`, `submit_answer`, `query_concept`, and `get_sources`.
- Web: `GET /ipas/cybersecurity` shows all four slices, cards, quizzes and review labels; `POST /api/ipas/cybersecurity/answer` grades visible questions. The routes are unchanged from Phase 1. Existing iPAS routes and APIs are unchanged.

The current text cards and processed teaching Markdown validate content flow. A later iteration can improve presentation without changing canonical citations.

## Focused validation

From the repository root:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ipas_cybersecurity -v
.\venv\Scripts\python.exe -m unittest tests.test_ipas_cybersecurity_phase4 -v
```

The tests check all four schemas, canonical page references, relation targets, sequence and comparison constraints, source hash guard, review transitions, cards and quiz linkage, runtime discovery, Web rendering/grading, and existing AI/Net-Zero skill registration. No full-deck OCR or processing is involved.

## Architecture lock status

v0.3 needed the additive v0.4 comparison matrix for page 80's multi-dimensional A–D table. Parallel concepts, typed relations, and ordered processes still load without migration. The local review gate can support a controlled manual pilot, but no actual generated assets have been human-approved yet. Chapter-scale generation is premature until visual transcription review, batch reviewer workflow, provenance for later exam material, and larger chapter navigation are addressed.
