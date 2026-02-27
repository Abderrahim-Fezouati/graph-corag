# Known Failure Modes

## Unicode logging crash on Windows
Symptom:
- `UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'`

Cause:
- Windows console encoding (cp1252) cannot print the arrow character.

Fix (logging-only):
- Replace `"->"` for the arrow in console prints, e.g. in `scripts/analyze_with_el_and_intent.py` and `scripts/run_ner_offline.py`.

## relation_not_in_kg
Symptom:
- `skipped_reason: relation_not_in_kg` in analyzed queries.

Cause:
- Predicted relation is not in KG relations (`INTERACTS_WITH`, `ADVERSE_EFFECT`, `CONTRAINDICATED_FOR`).

Resolution:
- Ensure relation prediction or query patterns map to a KG-supported predicate.

## head vs KG node mismatch
Symptom:
- `coverage = 0.0` despite correct KG having edges.

Cause:
- `head` is a surface string (e.g., "aldesleukin"), not a KG node id (e.g., `drug_aldesleukin`).
- `scripts/run_hybrid.py` prefers `head` over `head_cui`.

Resolution:
- Ensure `head` is a KG node id (drug_*/disease_*).

## Long first-run delays
Symptom:
- First run takes several minutes.

Cause:
- Model loading and local cache initialization (spaCy models, Transformers, SentenceTransformer).

Resolution:
- Allow time for initial load; reruns are faster once caches are populated.

## Not a bug: coverage = 0.0
Symptom:
- `coverage = 0.0` even with good text retrieval.

Cause:
- KG coverage is only set when an explicit KG neighbor edge exists for `(head, relation)`.

Resolution:
- Treat coverage as KG presence only, not text evidence.
