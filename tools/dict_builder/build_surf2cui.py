import json, sys
from pathlib import Path

base, overlay, out_node2surfs, out_surf2cui = sys.argv[1:]
data = {}
if Path(base).exists():
    data = json.loads(Path(base).read_text(encoding="utf-8"))

if Path(overlay).exists():
    over = json.loads(Path(overlay).read_text(encoding="utf-8"))
    for cui, surfs in (over or {}).items():
        lst = data.setdefault(cui, [])
        seen = {(s or "").strip().lower() for s in lst}
        for s in surfs or []:
            s = (s or "").strip()
            if s and s.lower() not in seen:
                lst.append(s)
                seen.add(s.lower())

# write merged node->surfaces (nice to keep)
Path(out_node2surfs).write_text(
    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
)

# invert to surface->CUI for the retriever
surf2cui = {}
for cui, surfs in data.items():
    for s in surfs or []:
        k = (s or "").strip().lower()
        if k:
            surf2cui[k] = str(cui).strip().upper()

Path(out_surf2cui).write_text(
    json.dumps(surf2cui, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"surfaces: {len(surf2cui)}    CUIs: {len(data)}")
