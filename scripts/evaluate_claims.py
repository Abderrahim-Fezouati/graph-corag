# -*- coding: utf-8 -*-
"""
Evaluate KG claim validation results.

Metrics:
- Verdict distribution
- Precision@KG
- Predicate-wise statistics
- Claim volume per query

Paper-grade, fully automatic.
"""

import json
import argparse
from collections import Counter, defaultdict
from typing import Dict


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="hybrid.outputs.jsonl")
    ap.add_argument("--out", default=None, help="optional JSON summary output")
    args = ap.parse_args()

    verdict_counter = Counter()
    predicate_verdicts = defaultdict(Counter)
    claims_per_query = []
    total_claims = 0

    for row in load_jsonl(args.input):
        claims = row.get("claims", [])
        validations = row.get("kg_validation", [])

        claims_per_query.append(len(claims))
        total_claims += len(claims)

        for v in validations:
            verdict = v["verdict"]
            verdict_counter[verdict] += 1

        for c, v in zip(claims, validations):
            pred = c.get("predicate", "UNKNOWN")
            verdict = v["verdict"]
            predicate_verdicts[pred][verdict] += 1

    # ----------------------------
    # Precision@KG
    # ----------------------------
    supported = verdict_counter["supported"]
    contradicted = verdict_counter["contradicts"]

    precision_at_kg = (
        supported / (supported + contradicted)
        if (supported + contradicted) > 0
        else 0.0
    )

    # ----------------------------
    # Report
    # ----------------------------
    print("\n=== Claim Validation Evaluation ===\n")

    print("Total claims:", total_claims)
    print(
        "Claims per query (avg):", sum(claims_per_query) / max(1, len(claims_per_query))
    )

    print("\nVerdict distribution:")
    for k, v in verdict_counter.items():
        print(f"  {k:12s}: {v}")

    print("\nPrecision@KG:")
    print(f"  {precision_at_kg:.4f}")

    print("\nPredicate-wise breakdown:")
    for pred, ctr in predicate_verdicts.items():
        total = sum(ctr.values())
        supp = ctr["supported"]
        rate = supp / total if total > 0 else 0.0
        print(f"  {pred:16s} supported={supp}/{total} ({rate:.2%})")

    # ----------------------------
    # Optional JSON output
    # ----------------------------
    if args.out:
        out = {
            "total_claims": total_claims,
            "verdict_distribution": dict(verdict_counter),
            "precision_at_kg": precision_at_kg,
            "predicate_breakdown": {p: dict(c) for p, c in predicate_verdicts.items()},
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

        print(f"\n[OK] Wrote evaluation summary → {args.out}")


if __name__ == "__main__":
    main()
