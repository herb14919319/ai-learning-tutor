# Learning Chunk v0.2 stress test — three-step risk assessment

Canonical source: `knowledge/source/iPAS_資訊安全管理概論_PART_I.pdf`, one-based PDF pages **103** and **105**. Page 103 is titled `風險管理的流程 - 風險評鑑階段`; it states the assessment purpose and says assessment can be iterative. Page 105 is titled `風險管理的流程 - 風險評鑑階段詳細風險評鑑`; its bullets and vertical arrows explicitly order **風險識別 → 風險分析 → 風險評估**. Page 104's high-level assessment comparison was reviewed as context but is outside this slice. The larger five-stage management lifecycle on page 99 is also out of scope.

## v0.2 trial before changing it

- `chunk_type=process` supports a separately cited chunk for each step. `source_evidence` can cite the same page for several semantic steps without treating the slide as one chunk. `related_concepts` can link them for navigation.
- v0.2's typed predicates are `exploits`, `belongs_to`, and `contributes_to`. None means **precedes**. Using `contributes_to` for step order would misstate the source; prose-only order could not be checked for a reversed or cyclic chain.
- No separate `step_number`, `follows`, `depends_on`, `produces`, or `part_of` field is needed. The visible arrows justify only the directed `precedes` relation for this slice. Step descriptions state what each phase does; the teaching section explains the transition.

## Minimal decision

v0.3 extends v0.2 by adding **only** the `precedes` predicate to the existing optional relationship list. A small loader check requires `precedes` links to stay within one slice and form a single acyclic chain across that slice's process chunks. CIA v0.1 and Risk v0.2 files remain unchanged. Iteration described on page 103 means the assessment can be revisited, not that the three within-pass arrows lose their order; this schema records the order of one pass and does not model a general workflow loop.
