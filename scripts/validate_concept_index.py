import json, csv, re
from pathlib import Path

KG = Path(r"F:\graph-corag-clean\data\kg_edges.merged.plus.csv")
DR = Path(r"F:\graph-corag-clean\artifacts\concept_index\drug\rows.jsonl")
DI = Path(r"F:\graph-corag-clean\artifacts\concept_index\disease\rows.jsonl")


def load_ids_from_kg(kpath):
    ids = set()
    with kpath.open(encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            ids.add(row.get("head"))
            ids.add(row.get("tail"))
    return {x for x in ids if x}


def looks_node_id(s):
    return bool(
        re.match(
            r"^(drug_|disease_|gene_|chemical_|rxnorm:|chebi:|drugbank:)",
            (s or ""),
            re.I,
        )
    )


def sample(path, n=5):
    out = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            out.append(json.loads(line))
    return out


kg_ids = load_ids_from_kg(KG)
ok = True
for path in [DR, DI]:
    s = sample(path)
    for r in s:
        kid = r.get("kg_id")
        txt = r.get("text")
        if not looks_node_id(kid):
            print("FAIL: kg_id is not a node id:", kid, "in", path.name)
            ok = False
        if looks_node_id(txt):
            print("FAIL: text looks like a node id:", txt, "in", path.name)
            ok = False
        if kid not in kg_ids:
            print("WARN: kg_id not found in KG:", kid, "in", path.name)
print("VALIDATION:", "OK" if ok else "PROBLEMS FOUND")
