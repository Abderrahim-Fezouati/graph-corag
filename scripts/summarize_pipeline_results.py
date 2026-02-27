import json
import argparse
import pandas as pd


def extract_verdict_counts(kg_verdicts):
    """Return #edges_supported and comma-joined edges."""
    if not kg_verdicts:
        return 0, ""
    edges = []
    for v in kg_verdicts:
        edge = v.get("edge")
        present = v.get("present", False)
        if edge and present:
            edges.append(" | ".join(edge))
    return len(edges), "; ".join(edges)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input", required=True, help="hybrid.outputs.jsonl from your pipeline"
    )
    ap.add_argument("--out", required=True, help="TSV summary output")
    args = ap.parse_args()

    rows = []
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)

            qid = obj.get("qid")
            rels = ",".join(obj.get("relations", []))
            head = obj.get("head") or obj.get("head_cui")
            cov = obj.get("coverage", 0.0)
            dec = obj.get("decision")
            recall = obj.get("text_entity_recall@k", None)
            hops = obj.get("hops", None)

            verdicts = obj.get("kg_verdicts", [])
            n_edges_supported, edges_joined = extract_verdict_counts(verdicts)

            rows.append(
                {
                    "qid": qid,
                    "relation": rels,
                    "head_cui": head,
                    "coverage": cov,
                    "kg_edges_supported": n_edges_supported,
                    "supported_edges": edges_joined,
                    "decision": dec,
                    "text_recall": recall,
                    "hops": hops,
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(args.out, sep="\t", index=False)
    print(f"[DONE] Summary written to {args.out}")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
