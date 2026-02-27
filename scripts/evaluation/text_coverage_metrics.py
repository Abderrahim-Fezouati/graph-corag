import argparse, io, json, csv, re, os
from collections import defaultdict


def load_queries(path):
    qs = []
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            j = json.loads(line)
            # tolerate older query format (no qid)
            j["_qid"] = j.get("qid") or len(qs) + 1
            # prefer require_entities if present; else fall back to boost_terms or surface strings
            req = j.get("require_entities") or j.get("boost_terms") or []
            # normalize to unique, non-empty
            seen = set()
            req_clean = []
            for s in req:
                s2 = (s or "").strip()
                if s2 and s2.lower() not in seen:
                    seen.add(s2.lower())
                    req_clean.append(s2)
            j["_require"] = req_clean
            qs.append(j)
    return qs


def load_corpus(path):
    """Expect docs.jsonl with at least {id, text} or {doc_id, text}."""
    m = {}
    with io.open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            j = json.loads(line)
            did = j.get("id") or j.get("doc_id")
            if not did:
                continue
            m[did] = j.get("text", "")
    return m


def _hit_doc_id(hit):
    """Return doc_id from a hit that might look like:
    "PMID:123#c0" OR ["score", "doc_id"] OR {"doc_id":..., "score":...} OR (score, doc_id)
    """
    if isinstance(hit, str):
        return hit
    if isinstance(hit, (list, tuple)) and len(hit) >= 2:
        # assume (score, doc_id)
        return hit[1]
    if isinstance(hit, dict):
        return hit.get("doc_id") or hit.get("id")
    return None


def load_cache(path):
    """Expect JSONL lines with at least {qid, hits} OR {query_index, hits} OR in-order with implicit qid."""
    records = []
    with io.open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            j = json.loads(line)
            qid = j.get("qid") or j.get("query_index")
            records.append((qid, j.get("hits") or j.get("retrieved") or []))
    # If qids missing, fill sequentially starting at 1
    if any(qid is None for qid, _ in records):
        records = list(enumerate([h for _, h in records], start=1))
    return records  # list of (qid, hits)


def entities_in_text(text, entities):
    t = text.lower()
    found = set()
    for e in entities:
        if e.lower() in t:
            found.add(e)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out_per_query", required=True)
    ap.add_argument("--out_summary", required=True)
    ap.add_argument("--ks", type=int, nargs="+", default=[1, 5, 10, 50, 150])
    args = ap.parse_args()

    qs = load_queries(args.queries)
    doc_map = load_corpus(args.corpus)
    cache = load_cache(args.cache)

    # Index queries by qid
    q_by_id = {q["_qid"]: q for q in qs}

    # Prepare per-query results
    rows = []
    totals = {k: {"complete": 0, "partial": 0, "zero": 0} for k in args.ks}

    for qid, hits in cache:
        q = q_by_id.get(qid)
        if not q:
            # cache and query file are out of sync; skip
            continue
        req = q["_require"]
        if not req:
            continue
        # Resolve doc texts for the ranked list
        ranked_docs = []
        for h in hits:
            did = _hit_doc_id(h)
            if not did:
                continue
            ranked_docs.append(doc_map.get(did, ""))

        for k in args.ks:
            top_text = " ".join(ranked_docs[:k])
            found = entities_in_text(top_text, req)
            missing = [e for e in req if e not in found]
            status = (
                "complete"
                if len(found) == len(req)
                else ("zero" if len(found) == 0 else "partial")
            )
            totals[k][status] += 1

            rows.append(
                {
                    "qid": qid,
                    "k": k,
                    "query_text": q.get("text", ""),
                    "required_total": len(req),
                    "found_count": len(found),
                    "status": status,
                    "missing": " | ".join(missing),
                }
            )

    # Write per-query CSV
    os.makedirs(os.path.dirname(args.out_per_query), exist_ok=True)
    with io.open(args.out_per_query, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "qid",
                "k",
                "query_text",
                "required_total",
                "found_count",
                "status",
                "missing",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    # Write summary text
    total_qs = len({r["qid"] for r in rows}) if rows else 0
    with io.open(args.out_summary, "w", encoding="utf-8") as f:
        f.write(f"[text coverage summary] queries={total_qs}\n")
        for k in args.ks:
            t = totals[k]
            comp = t["complete"]
            part = t["partial"]
            zero = t["zero"]
            pct = (comp / total_qs * 100.0) if total_qs else 0.0
            f.write(
                f"  @k={k}: complete={comp} ({pct:.1f}%)  partial={part}  zero={zero}\n"
            )


if __name__ == "__main__":
    main()
