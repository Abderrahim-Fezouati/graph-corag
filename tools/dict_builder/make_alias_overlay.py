import csv, json, re, os

inp = r"C:\\Users\\abder\\Desktop\\new experiment with Kg2c dataset\\data\\kg_edges.CANON.csv"  # kg_edges.CANON.csv
out = r"C:\\Users\\abder\\Desktop\\new experiment with Kg2c dataset\\config\\aliases.extra.json"  # aliases.extra.json


def variants(canon_id):
    m = re.match(
        r"^(drug|disease|gene|protein|chemical|metabolite|pathway|anatomy|cell|organism|exon|intron|rna|dna|enzyme|receptor|antibody|antigen)_(.+)$",
        canon_id,
    )
    base = m.group(2) if m else canon_id
    surf = base.replace("_", " ")
    cands = set([surf])

    # hyphen/space swaps
    cands.add(surf.replace(" ", "-"))
    cands.add(surf.replace("-", " "))
    # naive plural
    if not surf.endswith("s"):
        cands.add(surf + "s")
    # "mmp 13" <-> "mmp13"
    cands.add(re.sub(r"(\b[a-zA-Z]+)\s+(\d+)\b", r"\1\2", surf))
    cands.add(re.sub(r"(\b[a-zA-Z]+)(\d+)\b", r"\1 \2", surf))

    cands = {c.lower() for c in cands}
    cands = {c for c in cands if len(c) >= 3}
    return cands


nodes = set()
with open(inp, newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    for row in r:
        if not row or len(row) < 3:
            continue
        h, rel, t = [x.strip().strip('"') for x in row[:3]]
        nodes.add(h)
        nodes.add(t)

alias2id = {}
for nid in nodes:
    for s in variants(nid):
        alias2id.setdefault(s, nid)  # first-come wins

os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fo:
    json.dump(alias2id, fo, ensure_ascii=False, indent=2)

print("aliases:", len(alias2id))
