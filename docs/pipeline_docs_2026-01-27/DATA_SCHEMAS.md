# Data Schemas

All files are JSONL unless otherwise noted. Fields marked Required must be present for downstream stages.

## Raw queries JSONL (input)
Location examples:
- `data/queries_kg_aligned.jsonl`

Schema (per line):
```
{
  "qid": "T001",              // Required: unique query id
  "text": "..."              // Required: query text
}
```
Optional fields (if available upstream):
- `relation` or `predicate`
- `head` or `head_cui`
- `candidates` (list of entity candidates)

## Analyzed queries JSONL (output of `scripts/analyze_with_el_and_intent.py`)
Schema (per line):
```
{
  "qid": "T001",                      // Required
  "text": "...",                      // Required
  "retrieved_docs": ["PMID:..."],     // Required (may be empty)
  "predicted_relation": "ADVERSE_EFFECT" | "INTERACTS_WITH" | ...,
  "relation_in_kg": true | false,
  "skipped_reason": "relation_not_in_kg" | "no_kg_neighbors",   // Optional
  "head_cui": "drug_aldesleukin",     // Required for KG grounding
  "head_text": "aldesleukin",         // Optional but recommended
  "head_score": 0.0-1.0,               // Optional
  "head_source": "query_ner" | "query_json",
  "ungrounded_head": true | false,
  "claims": [                          // Optional list
    {
      "head_cui": "drug_*",
      "predicate": "ADVERSE_EFFECT" | "INTERACTS_WITH" | ...,
      "tail_cui": "disease_*" | "drug_*",
      "evidence_text": "...",
      "claim_strength": "HYPOTHESIS" | "SUPPORTED",
      "claim_source": "KG" | "TEXT"
    }
  ],
  "kg_validation": [ ... ],            // Optional, from KGValidator
  "kg_validation_summary": { ... }     // Optional
}
```

## Adapter / pipeline-ready queries JSONL
This is the input expected by `scripts/pipeline/run_pipeline.py`.

Schema (per line):
```
{
  "qid": "T001",                   // Required
  "text": "...",                   // Required
  "relations": ["ADVERSE_EFFECT"], // Required (list)
  "head": "drug_aldesleukin",      // Required, must be KG node id
  "candidates": [                   // Required, non-empty
    {
      "cui": "drug_aldesleukin",   // Required
      "score": 0.9,                  // Optional
      "source": "query_ner"         // Optional
    }
  ],
  "head_text": "aldesleukin"        // Optional
}
```

## queries.for_hybrid.jsonl (output of `scripts/pipeline/run_pipeline.py`)
Schema (per line):
```
{
  "qid": "T001",                   // Required
  "text": "...",                   // Required
  "relations": ["ADVERSE_EFFECT"], // Required
  "head": "drug_aldesleukin",      // Required (preferred KG key)
  "head_cui": "drug_aldesleukin"   // Required
}
```

## hybrid.outputs.jsonl (output of `scripts/run_hybrid.py`)
Base schema (per line):
```
{
  "qid": "T001",
  "text": "...",
  "relations": ["ADVERSE_EFFECT"],
  "head": "drug_aldesleukin",
  "head_cui": "drug_aldesleukin",
  "kg_verdicts": [ {"edge": ["head","rel","tail"], "present": true} ],
  "coverage": 0.0 | 1.0,
  "decision": "supported" | "insufficient_text_support",
  "text_entity_recall@k": 0.0-1.0,
  "hops": 1
}
```
Additional fields when `scripts/pipeline/run_pipeline.py` injects reasoning:
```
{
  "kg_paths": [ ["h","r","t"], ... ],
  "reasoning_hops": 0-3,
  "explanations": ["h -[r]-> t", ...],
  "support_score": 0.0-1.0
}
```

## rl_eval.tsv (output of `scripts/run_hybrid.py`)
Header:
```
qid,qtype,rel,goal,phase,coverage,ter,top1_score,top1_id,reward,hops
```
Values are per-query evaluation and retrieval summaries.

## head vs head_cui vs head_text
- `head` is the preferred KG key used by `scripts/run_hybrid.py`.
- `head_cui` is the KG node id (in this KG, it looks like `drug_*` or `disease_*`).
- `head_text` is the surface text (human-readable), not necessarily a KG key.
- If `head` is a surface string (e.g., "aldesleukin"), KG lookup will fail even if `head_cui` is correct.
