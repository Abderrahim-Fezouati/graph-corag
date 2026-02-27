import json, sys, re
from collections import OrderedDict

"""
Patch: build head/tail CUIs for INTERACTS_WITH if two distinct CUIs are found in text.
Also sanitize bad head_cui leftovers (e.g., "of", "event", broken tokens).
INPUT:  --in <jsonl>  --dict <umls_dict.txt>  --out <jsonl>
Each input line: {"qid": "...", "question": "...", "relations": ["..."], ...}
"""


def load_dict(path):
    surf2cui = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # expected: surface\tCUI or surface\tcui_id
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            surf = parts[0].strip().lower()
            cui = parts[1].strip()
            if not surf or not cui:
                continue
            surf2cui.setdefault(surf, set()).add(cui)
    return surf2cui


def normalize_text(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def looks_like_cui(x):
    # Accept your project-style node ids like "drug_xxx", "disease_xxx", etc.
    return bool(
        re.match(
            r"^(drug|disease|gene|chemical|procedure|exposure|food|device|organism|pathway|phenotype|symptom)_[a-z0-9_]+$",
            str(x),
        )
    )


def extract_all_cuis(text, surf2cui):
    t = " " + normalize_text(text) + " "
    # Greedy longest-first matching by surface length
    surfaces = sorted(surf2cui.keys(), key=len, reverse=True)
    hits = []
    used_spans = []

    for s in surfaces:
        # fast prune
        if s not in t:
            continue
        # find non-overlapping matches
        start = 0
        while True:
            idx = t.find(" " + s + " ", start)
            if idx == -1:
                break
            span = (idx, idx + len(s) + 2)
            # reject if overlapping a previous span
            if any(not (span[1] <= a or span[0] >= b) for (a, b) in used_spans):
                start = idx + 1
                continue
            for cui in surf2cui[s]:
                hits.append((idx, s, cui))
            used_spans.append(span)
            start = idx + 1

    # sort by appearance order; keep the first CUI seen per surface occurrence
    hits.sort(key=lambda x: x[0])
    ordered = []
    seen = set()
    for _, s, cui in hits:
        key = (s, cui)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cui)
    # de-duplicate CUIs while preserving order
    uniq = list(OrderedDict.fromkeys(ordered))
    return [c for c in uniq if looks_like_cui(c)]


def main():
    # very small CLI
    arg = sys.argv[1:]
    try:
        inp = arg[arg.index("--in") + 1]
        dictp = arg[arg.index("--dict") + 1]
        outp = arg[arg.index("--out") + 1]
    except Exception:
        print(
            "Usage: python prep_hinted_queries.py --in in.jsonl --dict umls_dict.txt --out out.jsonl",
            file=sys.stderr,
        )
        sys.exit(2)

    surf2cui = load_dict(dictp)

    with open(inp, "r", encoding="utf-8") as fin, open(
        outp, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            if not line.strip():
                continue
            ex = json.loads(line)
            qtext = ex.get("text") or ex.get("question") or ""
            rels = ex.get("relations") or []
            cuis = extract_all_cuis(qtext, surf2cui)

            # clean up any stale/bad head_cui that may be present
            head_cui = ex.get("head_cui")
            if head_cui and not looks_like_cui(head_cui):
                head_cui = None

            # For INTERACTS_WITH, write both if we have >=2 distinct CUIs
            if "INTERACTS_WITH" in rels:
                if len(cuis) >= 2:
                    ex["head_cui"] = head_cui or cuis[0]
                    ex["tail_cui"] = (
                        cuis[1]
                        if cuis[1] != ex["head_cui"]
                        else (cuis[2] if len(cuis) > 2 else None)
                    )
                elif len(cuis) == 1:
                    # keep at least a valid head; tail left empty to let runner fallback
                    ex["head_cui"] = head_cui or cuis[0]
                else:
                    # nothing found; leave as-is to use fallback in runner
                    pass
            else:
                # non-DDI: keep any good head_cui if present; otherwise seed with first found
                if not head_cui and len(cuis) >= 1:
                    ex["head_cui"] = cuis[0]

            fout.write(json.dumps(ex, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
