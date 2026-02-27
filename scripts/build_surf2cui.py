# -*- coding: utf-8 -*-
# Build surface->CUI mapping from (CUI -> [surfaces]) + optional overlay.
import json, argparse, sys
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="in_path", required=True)
ap.add_argument("--overlay", dest="overlay_path", default=None)
ap.add_argument("--out", dest="out_path", required=True)
args = ap.parse_args()


def load_cui2surfs(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_overlay(base, overlay):
    if not overlay:
        return base
    try:
        ov = load_cui2surfs(overlay)
    except Exception:
        return base
    for cui, surfs in ov.items():
        base.setdefault(cui, [])
        base[cui] = list({*(s.strip() for s in base[cui]), *(s.strip() for s in surfs)})
    return base


cui2 = load_cui2surfs(args.in_path)
cui2 = merge_overlay(cui2, args.overlay_path)

surf2 = defaultdict(set)
for cui, surfs in cui2.items():
    for s in surfs:
        s = s.strip()
        if not s:
            continue
        surf2[s.lower()].add(cui)

# convert sets to sorted lists for JSON
surf2 = {k: sorted(v) for k, v in surf2.items()}

with open(args.out_path, "w", encoding="utf-8") as f:
    json.dump(surf2, f, ensure_ascii=False, indent=2)

print(
    f"Built surface->CUI: {len(surf2)} surfaces from {len(cui2)} CUIs -> {args.out_path}"
)
