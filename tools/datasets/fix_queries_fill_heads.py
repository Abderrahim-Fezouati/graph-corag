# -*- coding: utf-8 -*-
import argparse, json, re, sys, io, os

VALID_PREFIXES = (
    "drug_",
    "disease_",
    "gene_",
    "chemical_",
    "procedure_",
    "exposure_",
    "food_",
    "device_",
    "organism_",
    "pathway_",
    "phenotype_",
    "symptom_",
)
AE_OR_DDI = {"ADVERSE_EFFECT", "INTERACTS_WITH"}


def looks_like_cui(x: str) -> bool:
    return bool(
        re.match(
            r"^(?:drug|disease|gene|chemical|procedure|exposure|food|device|organism|pathway|phenotype|symptom)_[a-z0-9_]+$",
            str(x or ""),
        )
    )


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = (
        s.replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2019", "'")
        .replace("â€‘", "-")
    )
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return s


def load_overlay(path):
    if not path or not os.path.exists(path):
        return {}
    with io.open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            return {}
    return {normalize_text(k).lower(): v for k, v in data.items()}


def load_dict(path):
    if not path or not os.path.exists(path):
        return {}
    if path.lower().endswith(".json"):
        with io.open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        mapping = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    mapping[normalize_text(k).lower()] = v
                elif isinstance(v, list):
                    for alias in v:
                        mapping[normalize_text(alias).lower()] = k
        return mapping
    mapping = {}
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\t+", line, maxsplit=1)
            if len(parts) == 2:
                surface, cui = parts
                mapping[normalize_text(surface).lower()] = cui.strip()
    return mapping


def best_cui_for_question(qtext: str, rels, overlay_map, dict_map):
    qnorm = normalize_text(qtext).lower()
    if qnorm in overlay_map and looks_like_cui(overlay_map[qnorm]):
        return overlay_map[qnorm]
    if qnorm in dict_map and looks_like_cui(dict_map[qnorm]):
        return dict_map[qnorm]
    candidates = []
    for surface, cui in dict_map.items():
        if not looks_like_cui(cui):
            continue
        if len(surface) < 3:
            continue
        if surface in qnorm:
            candidates.append((len(surface), surface, cui))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    if any(r in AE_OR_DDI for r in (rels or [])):
        for _, _, cui in candidates:
            if cui.startswith("drug_"):
                return cui
    return candidates[0][2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--dict", dest="dict_path", required=True)
    ap.add_argument("--overlay", dest="overlay_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    args = ap.parse_args()

    overlay_map = load_overlay(args.overlay_path)
    dict_map = load_dict(args.dict_path)

    fixed = total = 0
    with io.open(args.in_path, "r", encoding="utf-8") as fin, io.open(
        args.out_path, "w", encoding="utf-8", newline="\n"
    ) as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
            except Exception:
                continue
            total += 1
            ex["text"] = normalize_text(ex.get("text") or ex.get("question") or "")
            ex["question"] = ex.get("question") or ex["text"]
            rels = ex.get("relations") or []
            head = ex.get("head_cui")
            if not looks_like_cui(head):
                inferred = best_cui_for_question(
                    ex["text"], rels, overlay_map, dict_map
                )
                if inferred:
                    ex["head_cui"] = inferred
                    fixed += 1
                else:
                    ex["head_cui"] = None
            tail = ex.get("tail_cui")
            if not looks_like_cui(tail):
                ex["tail_cui"] = None
            fout.write(json.dumps(ex, ensure_ascii=False) + "\n")
    sys.stderr.write(f"Processed {total}, fixed heads: {fixed}\n")


if __name__ == "__main__":
    main()
