import csv, json
from pathlib import Path

KG = Path(r"F:\graph-corag-clean\data\kg_edges.merged.plus.csv")
DR = Path(r"F:\graph-corag-clean\artifacts\concept_index\drug\rows.jsonl")
DI = Path(r"F:\graph-corag-clean\artifacts\concept_index\disease\rows.jsonl")


def load_kg_nodes():
    ids = set()
    with KG.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        hk = tk = None
        # robust header
        cols = [(c or "").strip().lower().lstrip("\ufeff") for c in r.fieldnames]
        if "head" in cols:
            hk = r.fieldnames[cols.index("head")]
        if "tail" in cols:
            tk = r.fieldnames[cols.index("tail")]
        for row in r:
            if hk and row.get(hk):
                ids.add(row[hk].strip())
            if tk and row.get(tk):
                ids.add(row[tk].strip())
    return ids


def prune(path, allowed):
    keep = 0
    total = 0
    tmp = path.with_suffix(".jsonl.tmp")
    with path.open("r", encoding="utf-8") as f, tmp.open("w", encoding="utf-8") as w:
        for line in f:
            total += 1
            obj = json.loads(line)
            if obj.get("kg_id") in allowed:
                w.write(line)
                keep += 1
    tmp.replace(path)
    print(f"[{path.name}] kept {keep}/{total}")


nodes = load_kg_nodes()
for p in [DR, DI]:
    prune(p, nodes)
