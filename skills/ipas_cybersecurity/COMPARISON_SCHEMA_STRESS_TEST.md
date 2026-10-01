# Phase 4: v0.3 comparison stress test

## Bounded source

Canonical file: `knowledge/source/iPAS_資訊安全管理概論_PART_I.pdf`, one-based PDF pages **77–80**. Visible titles: p.77 `資訊資產項目`, p.78 `資訊資產蒐集與管理`, p.79 `資訊資產清冊`, p.80 `資訊資產價值分類`. Page 76 is the section divider; page 81 starts physical security and is excluded. The four pages contain asset types, a collection/classification/control cycle, a sample register, and an A–D classification matrix. The six other source PDFs and exam references were not processed.

The page 80 matrix compares four levels along three independent dimensions: the described affected scope, business damage condition, and potential impact level. A/B/C state one month/one week/one day **including** the stated duration, respectively; D says an incident does not affect business work or operations and gives no duration threshold. This asymmetry matters. The table is a source-specific example, not a universal classification rule.

## Attempt with v0.3 unchanged

v0.3 can hold the seven concept chunks and their page citations. `related_concepts` can identify the four levels as adjacent. Typed directed relations and `precedes` are unsuitable: A–D are compared, not a causal chain or workflow. A prose paragraph could describe all three dimensions, but the loader could not verify that each level has one value per dimension or that a question references the comparison. A generic `comparison` chunk type existed, but it carried no structured comparison fields. That is the demonstrated limitation.

## Minimal v0.4 change

Only the summary comparison chunk has an optional `source_evidence.comparison` object: ordered `members` and `dimensions`, each with a stable key, label and one source-page-cited value per member. This is a reviewed transcription/index of page 80, **not** a replacement for the PDF. The loader validates same-slice member IDs, unique dimensions, one value per member and dimension, source-page membership, and optional question `comparison_chunk_id`. It cannot mechanically prove that image-only source text was transcribed correctly; the page 80 visual review and human gate remain necessary.

CIA stays on v0.1, Risk on v0.2, Assessment on v0.3; no chunk migration or graph subsystem is needed. v0.4 introduces no new relationship predicate. The seven pilot chunks, ten cards, and ten questions remain pending review.
