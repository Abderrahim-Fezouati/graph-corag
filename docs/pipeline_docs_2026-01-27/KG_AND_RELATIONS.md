# KG and Relations

## KG node ID format
The KG in `data/kg_edges.merged.plus.csv` uses node ids like:
- `drug_*` (e.g., `drug_aldesleukin`)
- `disease_*` (e.g., `disease_autoimmune_reaction`)

These are the canonical KG keys and should be used for `head` and `head_cui` in pipeline inputs.

## Supported KG predicates (only)
The KG relation column includes exactly these predicates:
- `INTERACTS_WITH`
- `ADVERSE_EFFECT`
- `CONTRAINDICATED_FOR`

No other predicates are supported by the KG.

## Why CAUSES is unsupported
`CAUSES` does not appear in `data/kg_edges.merged.plus.csv`. Any query predicted as `CAUSES` is not in the KG relation set, and will be marked `relation_not_in_kg` during analysis.

## relation_not_in_kg
This arises in `scripts/analyze_with_el_and_intent.py` when the predicted relation is not found in the KG predicate set. The query is skipped for KG validation and emits `skipped_reason: relation_not_in_kg`.

## KG coverage semantics
In `scripts/run_hybrid.py`, coverage is computed as:
- `coverage = 1.0` only if there is at least one KG neighbor for `(head, relation)`.
- `coverage = 0.0` if no neighbors exist, or if `head` is missing or not a KG key.

Coverage is a KG presence check; it is not a textual evidence score.
