# Learning Chunk v0.1 stress test — risk concept group

Reviewed canonical source: `knowledge/source/iPAS_資訊安全管理概論_PART_I.pdf`, one-based PDF pages **92, 93, 95**. Page 94 (`認識風險管理`) was read as context only. These pages are later than CIA because the intervening slides cover ISMS, ethics, assets and physical security. The topic is kept to the smallest clear definition/relationship group; the later risk-management process is out of scope.

| PDF page | Visible title | Relevant structure |
| --- | --- | --- |
| 92 | `風險的定義` | Text and a causal diagram: 威脅 exploits 脆弱性 associated with an 資產, produces 衝擊; the diagram and prose connect 衝擊 and 可能性 to 風險. |
| 93 | `風險的定義` | ISO 31000:2018 framing of risk as uncertainty's effect on organizational objectives; notes likelihood and impact. This is a broader framing than the simplified security example. |
| 95 | `認識風險管理` | Compact restatement using Threat, Asset, Vulnerability, Impact, Likelihood; illness analogy varies vulnerability or likelihood and shows risk differs. A small risk-identification → analysis → evaluation diagram is contextual and **not** processed as a full workflow. |

## v0.1 findings before changing it

- **Works:** `source_evidence.source_pages` spans several pages; `source_title` and observations preserve the visible source; `chunk_type=comparison` can hold impact versus likelihood; `teaching_interpretation.explanation` and `exam_focus` cover exam distinctions. `related_concepts` validates that IDs exist.
- **Awkward:** `related_concepts` is an untyped list. It cannot say that a threat **exploits** a vulnerability, that a vulnerability **affects** an asset, or that impact and likelihood **contribute to** risk. Those relations are explicit in page 92's diagram and page 95's sentence, and collapsing them into prose prevents a loader from validating the intended dependency. v0.1 can store the prose, but the relationship is not structured.
- **Not needed now:** an ordering field or process schema. The three-step assessment arrow on page 95 is outside this definition slice; the source requirement here is a small set of typed relations, not a risk-workflow model.

## Minimal decision

Introduce v0.2 with one optional top-level `relationships` list. Each relation has `predicate` and `target_chunk_id`; the initial predicates are `exploits`, `belongs_to`, and `contributes_to`. The loader validates target IDs and allowed predicates. `related_concepts` remains required and serves broad navigation; `relationships` records only source-supported direction. Existing CIA chunks stay in v0.1 unchanged and load through the same runtime. No graph store or adaptive-learning subsystem is introduced.
