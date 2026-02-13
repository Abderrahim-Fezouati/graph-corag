# -*- coding: utf-8 -*- 
import argparse, json, sys, importlib.util, os
from typing import Any, Dict, List, Optional, Tuple

def _safe_cui(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("", "none", "null", "na", "n/a", "of"):  # guard "of" garbage value
        return None
    return str(v).strip()

def _load_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                print(f"[WARN] bad JSONL line: {e}", file=sys.stderr)
    return out

def _import_from_path(py_path: str, obj_name: str):
    spec = importlib.util.spec_from_file_location("mod_"+obj_name, py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {obj_name} from {py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, obj_name)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--proj",    type=str, required=False, default="")
    p.add_argument("--corpus",  type=str, required=True)
    p.add_argument("--kg",      type=str, required=True)
    p.add_argument("--dict",    type=str, required=True)
    p.add_argument("--overlay", type=str, required=True)
    p.add_argument("--schema",  type=str, required=True)
    p.add_argument("--queries", type=str, required=True)
    p.add_argument("--out",     type=str, required=True)

    p.add_argument("--topk", type=int, default=80)
    p.add_argument("--min_constraints", type=int, default=2)
    p.add_argument("--mode", choices=["text","kg","both"], default="both")
    p.add_argument(
        "--bm25_mod_path",
        type=str,
        required=False,
        default=None,
        help="Optional. If omitted, BM25 is built from --corpus at runtime."
    )
    p.add_argument("--dense_mod_path", type=str, required=True)

    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    out_path  = os.path.join(args.out, "hybrid.outputs.jsonl")
    rl_path   = os.path.join(args.out, "rl_eval.tsv")

    # Log only to terminal (no log file on disk)
    log = sys.stdout

    # Import retrievers
    if args.bm25_mod_path is None:
        from graphcorag.text_retriever import TextRetriever
        bm25 = TextRetriever(args.corpus, args.dict, args.overlay)
        print("[INFO] BM25: Built dynamically from corpus at runtime.")
    else:
        raise NotImplementedError(
            "Indexed BM25 not implemented; omit --bm25_mod_path to use dynamic BM25."
        )
    DenseRetriever = _import_from_path(args.dense_mod_path, "DenseRetriever")
    dense = DenseRetriever(args.corpus)

    # Minimal KG interface (expects CSV h,r,t headers or no header)
    def iter_kg_edges():
        import csv
        with open(args.kg, "r", encoding="utf-8") as f:
            r = csv.reader(f)
            peek = next(r)
            has_hdr = (len(peek) >= 3 and {"h","r","t"}.issubset({x.strip().lower() for x in peek}))
            if not has_hdr:
                yield tuple(peek[:3])
            for row in r:
                if not row:
                    continue
                yield tuple(row[:3])

    # Build quick neighbor index for INTERACTS_WITH / ADVERSE_EFFECT
    from collections import defaultdict
    nbr: dict[tuple[str, str], list[str]] = defaultdict(list)
    for h, r, t in iter_kg_edges():
        r2 = r.strip()
        if r2 in ("INTERACTS_WITH", "ADVERSE_EFFECT"):
            nbr[(h.strip(), r2)].append(t.strip())

    examples = _load_jsonl(args.queries)

    with open(out_path, "w", encoding="utf-8") as jout, \
         open(rl_path, "w", encoding="utf-8") as rl:

        rl.write("qid,qtype,rel,goal,phase,coverage,ter,top1_score,top1_id,reward,hops\n")

        for qi, ex in enumerate(examples, start=1):
            qid   = ex.get("qid", f"Q{qi}")
            qtext = ex.get("text") or ex.get("question") or ""
            rels  = ex.get("relations") or []

            # Prefer canonical head if present, else fall back to head_cui
            head_raw = ex.get("head") or ex.get("head_cui")
            head = _safe_cui(head_raw)

            qtype = "unknown"
            hop_count = 1

            # TEXT side
            if args.mode == "text":
                bm = bm25.search(qtext, topk=args.topk)
                de = []
            elif args.mode == "kg":
                bm = []
                de = dense.search(qtext, topk=args.topk)
            else:
                bm = bm25.search(qtext, topk=args.topk)
                de = dense.search(qtext, topk=args.topk)

            # naive merge: prefer dense score if same doc id appears
            scores: dict[Any, float] = {}
            for doc_id, score in bm:
                scores[doc_id] = max(scores.get(doc_id, 0.0), float(score))

            for _hit in de:
                # accept dicts or tuples
                if isinstance(_hit, dict):
                    doc_id = _hit.get("id") or _hit.get("doc_id") or _hit.get("document_id")
                    score  = float(_hit.get("score", 0.0))
                elif isinstance(_hit, (list, tuple)) and len(_hit) >= 2:
                    a, b = _hit[0], _hit[1]
                    # tolerate (score, id) or (id, score)
                    if isinstance(a, (int, float)) and not isinstance(b, (int, float)):
                        doc_id, score = b, float(a)
                    else:
                        doc_id, score = a, float(b)
                else:
                    continue
                if doc_id is None:
                    continue
                scores[doc_id] = max(scores.get(doc_id, 0.0), float(score))

            top_sorted = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:args.topk]
            top1 = top_sorted[0] if top_sorted else ("N/A", 0.0)

            # KG side
            kg_verdicts: list[dict[str, Any]] = []
            coverage = 0.0
            if rels and head:
                for rel in rels:
                    rel = rel.strip()
                    if (head, rel) in nbr:
                        # collect neighbors briefly
                        for t in nbr[(head, rel)][:8]:
                            kg_verdicts.append({"edge": (head, rel, t), "present": True})
                        coverage = 1.0 if kg_verdicts else 0.0
                        qtype = "ddi" if rel == "INTERACTS_WITH" else "ae"
                        break  # take the first relation that hits

            decision = "supported" if coverage > 0 else "insufficient_text_support"
            reward   = 1.0 if coverage > 0 else 0.0
            ter      = float(len(top_sorted))/float(args.topk or 1)

            print("=" * 80, file=log)
            print(f"Query {qi}: {qtext}", file=log)
            print(f"text_topk: {len(top_sorted)} results; top1=({top1[0]}, {top1[1]})", file=log)
            print(f"kg_verdicts: {kg_verdicts}", file=log)
            print(f"coverage: {coverage:.3f}", file=log)
            print(f"decision: {decision}", file=log)
            print(f"text_entity_recall@{args.topk}: {ter:.3f}", file=log)
            print(f"hops: {hop_count}", file=log)

            jrow = {
                "qid": qid,
                "text": qtext,
                "relations": rels,
                "head": head,
                "head_cui": head,
                "kg_verdicts": kg_verdicts,
                "coverage": coverage,
                "decision": decision,
                "text_entity_recall@k": ter,
                "hops": hop_count,
            }
            jout.write(json.dumps(jrow, ensure_ascii=False) + "\n")
            rl.write(f"{qi},{qtype},{rels[0] if rels else ''},{rels[0] if rels else ''},eval,{coverage:.3f},{ter:.3f},{top1[1]},{top1[0]},{reward},{hop_count}\n")

    print(f"Out:  {out_path}")
    print(f"RL:   {rl_path}")

if __name__ == "__main__":
    main()
