# Generated-content review gate

The canonical PDF and `source_evidence` fields are source locators and observations. The review gate applies **only** to generated teaching Markdown, a chunk's `teaching_interpretation`, cards, and questions. It never edits the source PDF or source observations.

Generated assets default to `pending_review` (including legacy CIA assets without an explicit field). The checked-in `knowledge/processed/review_decisions.json` now records the Phase 5 asset-management owner decisions; other assets retain their own effective review status. A reviewer may inspect an asset and record:

| Decision | Effective state | Runtime |
| --- | --- | --- |
| accept | reviewed | Visible with reviewed label |
| revise | revision_required | Hidden until changed; changed content returns to visible pending state; note required |
| reject | rejected | Hidden; note required |

Pending assets remain visible with an explicit pending label. This preserves the three existing pending slices and allows pilot review. It means learners can see unreviewed material, so this is a controlled pilot policy, not a claim of publication quality. Rejected/revision-required chunks hide the teaching section and cards/questions that depend on them. A changed generated payload invalidates its last decision by hash and becomes pending again; the old decision remains in the append-only history. A change to a referenced chunk also resets an accepted teaching section, card, or question to pending through a saved dependency hash. It does not automatically re-approve downstream content.

From the repository root:

```powershell
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py show chunk I11-ASSET-004
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py decide chunk I11-ASSET-004 accept --note "Checked against PDF p.80"
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py decide card I11-ASSET-F001 revise --note "Clarify the asset categories"
.\venv\Scripts\python.exe skills\ipas_cybersecurity\review.py decide question I11-ASSET-Q001 reject --note "Ambiguous option"
```

Kinds are `teaching` (chapter ID), `chunk` (chunk ID), `card` (card ID), and `question` (question ID). `show` prints only the generated payload and effective status. The command checks the canonical PDF hash before showing or recording a decision. A decision records kind, ID, decision, an exact generated-content snapshot and its SHA-256, dependency hashes, UTC timestamp and optional note. This preserves what was reviewed even after an edit. No reviewer identity or authentication is stored. A note on a revise decision preserves the requested change; the CLI refuses acceptance of that same unchanged payload. Edit the generated artifact separately, inspect it, then explicitly accept the revision.

## Provenance boundary

- `canonical_source`: the original PDF in `knowledge/source/`, guarded by `source_manifest.json`. It is read-only in this workflow. `source_evidence` contains page locators and observations, not reviewer decisions.
- A separately owner-verified transcription of an image-only source table is recorded in `matrix_reviews.json` with the source hash, exact matrix snapshot and hash, page locator and timestamp. This verification does not turn the transcription into the canonical PDF and does not review generated teaching.
- `generated_unreviewed`: teaching interpretations, teaching Markdown, cards and questions with no current valid acceptance. This includes `pending_review`, `revision_required` and `rejected`; only pending content is exposed under the pilot runtime policy.
- `generated_reviewed`: generated content with an explicit owner acceptance for its current content hash and dependency hashes. The status is `reviewed`; it does not mean official exam material.

There is no `official` state. This local CLI is sufficient for a bounded, manually operated pilot, but chapter-scale production should add batch review tooling, reviewer accountability and stronger source-transcription checks.
