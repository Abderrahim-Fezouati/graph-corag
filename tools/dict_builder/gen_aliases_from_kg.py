import csv, json, re
from pathlib import Path

KG = Path(r"F:\graph-corag-clean\data\kg_edges.merged.plus.csv")
OUT = Path(r"F:\graph-corag-clean\config\aliases.manual.jsonl")


def make_surface(kg_id: str) -> str:
    s = re.sub(r"^(drug|disease|gene|chemical)_", "", kg_id, flags=re.I)
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    seen = set()
    count = 0
    with KG.open(encoding="utf-8-sig", newline="") as f, OUT.open(
        "w", encoding="utf-8"
    ) as w:
        r = csv.DictReader(f)
        cols = [(c or "").strip().lower().lstrip("\ufeff") for c in r.fieldnames]
        hk = r.fieldnames[cols.index("head")] if "head" in cols else None
        tk = r.fieldnames[cols.index("tail")] if "tail" in cols else None
        for row in r:
            for k in (row.get(hk), row.get(tk)):
                if not k:
                    continue
                kid = k.strip()
                surf = make_surface(kid)
                key = (kid, surf.lower())
                if key in seen:
                    continue
                seen.add(key)
                count += 1
                w.write(
                    json.dumps({"kg_id": kid, "synonyms": [surf]}, ensure_ascii=False)
                    + "\n"
                )
    print(f"Wrote {count} alias rows to {OUT}")


if __name__ == "__main__":
    main()
