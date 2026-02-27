import json, csv, re, os, sys
from collections import defaultdict

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DICT = os.path.join(PROJ, "config", "umls_dict.txt")
OVER = os.path.join(PROJ, "config", "umls_dict.overlay.json")
KGCSV = os.path.join(PROJ, "data", "kg_edges.merged.csv")
OUTJS = os.path.join(PROJ, "out", "kg_catalog.aliases.json")

os.makedirs(os.path.join(PROJ, "out"), exist_ok=True)


def load_dict():
    # dict is a JSON (CUI -> [aliases]) stored as .txt in your repo
    with open(DICT, "r", encoding="utf-8") as f:
        d = json.load(f)
    return d


def load_overlay():
    try:
        with open(OVER, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def normalize(s):
    return re.sub(r"\s+", " ", s).strip()


keep_nodes = set()
with open(KGCSV, newline="", encoding="utf-8") as f:
    rdr = csv.reader(f)
    for row in rdr:
        if len(row) < 3:
            continue
        h, r, t = [c.strip().strip('"') for c in row[:3]]
        keep_nodes.add(h)
        keep_nodes.add(t)

base = load_dict()
overlay = load_overlay()

aliases = {}
for cui, names in base.items():
    if cui not in keep_nodes:
        continue
    cand = set(n for n in names if n and isinstance(n, str))
    # overlay merges
    for extra in overlay.get(cui, []):
        if isinstance(extra, str):
            cand.add(extra)
        elif isinstance(extra, dict):
            for v in extra.values():
                if isinstance(v, str):
                    cand.add(v)
                elif isinstance(v, list):
                    for s in v:
                        if isinstance(s, str):
                            cand.add(s)
    # small heuristics
    norm = set()
    for s in cand:
        s2 = normalize(s)
        norm.add(s2)
        norm.add(s2.lower())
        norm.add(re.sub(r"[-_]", " ", s2).lower())
    aliases[cui] = sorted({a for a in norm if 2 <= len(a) <= 100})

with open(OUTJS, "w", encoding="utf-8") as f:
    json.dump(aliases, f, ensure_ascii=False, indent=2)

print(
    f"[catalog] wrote {OUTJS} | nodes={len(aliases)} total_aliases={sum(len(v) for v in aliases.values())}"
)
