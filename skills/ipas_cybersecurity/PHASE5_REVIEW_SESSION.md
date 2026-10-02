# Phase 5 owner review session — asset-management pilot

Final owner-reviewed asset-management scope: **7/7 chunk interpretations accepted; page 80 matrix explicitly verified; revised teaching section accepted; 10/10 cards and 10/10 questions accepted**. Owner decisions are in `knowledge/processed/review_decisions.json`; the matrix verification, with its transcription snapshot and source hash, is in `knowledge/processed/matrix_reviews.json`. This document is a review aid, not a decision or a substitute for the canonical PDF.

Canonical source (read-only): `knowledge/source/iPAS_資訊安全管理概論_PART_I.pdf`, one-based PDF pp. **77–80**. The teaching deck is image-only. The observations below are the existing Phase 4 source notes; verify them against the original page image before accepting generated content, especially the visually transcribed comparison on p. 80. The review CLI's `show` command displays only generated content.

## Order and commands

Review upstream content first: **7 chunk interpretations → 1 teaching section → 10 cards → 10 questions**. From the repository root:

```powershell
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py show chunk I11-ASSET-001
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py show teaching I11-ASSET
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py show card I11-ASSET-F001
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py show question I11-ASSET-Q001
```

After the owner decides, use `decide <kind> <id> accept|revise|reject --note "…"`. Revise and reject require a note. A revise decision preserves the old generated-content snapshot, hides the asset, and requires an edit to the generated content followed by a **new explicit acceptance**; the CLI refuses acceptance of the unchanged payload. Source evidence stays unchanged. A rejected or revision-required chunk also hides the teaching section and cards/questions that cite it. A changed chunk resets earlier downstream acceptances to pending through saved dependency hashes. Do not infer approval of dependents from approval of a chunk.

## Chunk review cards

| ID | Source context to check | Generated interpretation to judge |
| --- | --- | --- |
| `I11-ASSET-001` | pp. 77–80: six asset categories; management cycle; blank register; A–D comparison table | Identify and register assets, then distinguish A–D by source impact conditions. It is a source-specific example, not a universal statutory scale. Check all three comparison dimensions. |
| `I11-ASSET-002` | p. 78 `資訊資產蒐集與管理`: register collection → classification/grouping → differentiated controls → management; keep register accurate and updated | Asset management is a continuing collection, classification, control and update cycle; omissions undermine later controls. |
| `I11-ASSET-003` | p. 79 `資訊資產清冊`: sample register headings include ID, category, name, description, responsible/custodian/user units and asset value | A register connects identification, responsibility and value; it differs from the p. 80 value-classification table. |
| `I11-ASSET-004` | p. 80 A row: national-security-sensitive information/systems; business impact lasting **one month (inclusive) or more**; **極高度** potential impact | A in this table corresponds to the highest potential impact; compare scope, time and label with B. |
| `I11-ASSET-005` | p. 80 B row: social order, livelihood systems and public privacy; **one week (inclusive) or more**; **高度** | B corresponds to high potential impact; do not classify from the word “privacy” alone. |
| `I11-ASSET-006` | p. 80 C row: local/county social order and people’s life/property; **one day (inclusive) or more**; **中度** | C corresponds to moderate potential impact; compare scope, time and label with B. |
| `I11-ASSET-007` | p. 80 D row: an incident does not affect business work or operations; **低度**. No duration threshold is written. | D corresponds to low potential impact; do not invent a “less than one day” threshold. |

The source p. 80 table also supplies `I11-ASSET-001.source_evidence.comparison`. It must be checked **cell by cell** against the PDF: four members × three dimensions (affected scope, business damage condition, potential impact). A correct chunk interpretation does not automatically validate the matrix transcription.

## Downstream queue and dependencies

Teaching: `I11-ASSET` (`asset_teaching.md`) summarizes all seven chunks and the p. 80 table.

Cards (show each front/back before deciding):

| ID | Chunk dependencies | ID | Chunk dependencies |
| --- | --- | --- | --- |
| F001 | 001 | F006 | 006 |
| F002 | 001, 002 | F007 | 007 |
| F003 | 003 | F008 | 001, 005 |
| F004 | 004 | F009 | 001, 003 |
| F005 | 004, 005 | F010 | 001, 004, 005, 006, 007 |

Questions (show each prompt, options, answer and explanation before deciding):

| ID | Chunk dependencies | ID | Chunk dependencies |
| --- | --- | --- | --- |
| Q001 | 001 | Q006 | 001, 006 |
| Q002 | 003 | Q007 | 002 |
| Q003 | 001, 004 | Q008 | 001, 005, 006 |
| Q004 | 001, 004, 005, 006, 007 | Q009 | 001, 003 |
| Q005 | 007 | Q010 | 002 |

All IDs in these two tables have the prefix `I11-ASSET-`. A changed or rejected upstream chunk calls for checking its listed dependents and the teaching section. Runtime hides dependent cards/questions while that chunk is revision-required or rejected. After the chunk changes, previously accepted downstream assets become pending; they require separate owner decisions.

## Usability observations to measure during owner review

Record the actual number of CLI invocations, whether seven individual chunk inspections are tolerable, time spent locating each PDF page, repeated steps, surprises in dependency visibility, and whether the saved snapshot makes a revision understandable. Do not treat tests or scripted decisions as owner decisions.

### First chunk session observations

- The owner made **eight explicit decisions** in the interactive session: seven `accept` responses and one `matrix verified`. No teaching, card or question decision was requested or recorded.
- The assistant issued seven `decide chunk … accept` CLI commands and one `matrix-verified` command. The seven chunks were displayed one at a time with their exact stored observations, exact generated interpretations and relevant source-page images. The source PDF hash and matrix transcription hash still match their recorded values.
- Reviewing seven chunks individually was feasible in this bounded pilot, but `show` supplies only generated content. Source context and dependency references required separate JSON inspection and PDF rendering. A future minimal CLI improvement should list the next pending asset together with its source pages, stored observations and dependent IDs.
- The owner later requested one teaching sentence revision. The `revise` record preserved the previous teaching snapshot and instruction; the edited teaching section received a separate explicit `accept`. No card or question revisions or rejections occurred. Dependency invalidation and rejection behavior still have automated test coverage only.

## Phase 5 closeout and schema decision

The accepted release scope is the seven asset chunks, the page 80 matrix transcription, one teaching section, ten flashcards and ten original questions. The teaching revision changed only the final sentence about review lifecycle. The decision ledger retains both teaching snapshots and the owner instruction. Each card and question has its own acceptance record; chunk or teaching acceptance did not promote them automatically.

**Learning Chunk Schema v0.4 — FROZEN FOR CONTROLLED CHAPTER GENERATION.** The asset-management comparison, evidence locators, relationships and review dependencies fit v0.4 without a demonstrated blocking structural defect. The freeze means stable for the next controlled production pilot, not permanent incompatibility with future improvements. No v0.5 is created. Batch-review ergonomics, reviewer identity, visual transcription workflow and publication policy remain intentionally unresolved for broader chapter-scale use.
