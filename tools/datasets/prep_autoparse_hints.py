# -*- coding: utf-8 -*-
import json, re, sys, io, os

# Usage: python prep_autoparse_hints.py <in_jsonl> <dict_txt> <out_jsonl>
# Expects input lines like: {"qid":"AE001","question":"...","text":"..."}
# Writes lines like:       {"qid":...,"question":...,"text":...,"relations":["ADVERSE_EFFECT"],"head_cui":"drug_xxx"}

AE_PAT = re.compile(
    r"(adverse|side[- ]?effect|safety|harm|untoward|complication|toxicit)", re.I
)
DDI_PAT = re.compile(
    r"(avoid(ed)? with|clash|co[- ]?prescrib|contraindicat|interact|co[- ]?medicat)",
    re.I,
)


def infer_relation(q):
    if DDI_PAT.search(q):
        return "INTERACTS_WITH"
    if AE_PAT.search(q):
        return "ADVERSE_EFFECT"
    # default to AE for “conditions/issues/problems”
    if re.search(r"(conditions?|issues?|problems?)", q, re.I):
        return "ADVERSE_EFFECT"
    return "ADVERSE_EFFECT"


def load_dict(dict_path):
    # Expected format per line (most common in your setup): surface<TAB>CUI
    # Tolerant parse: split on tabs or whitespace, keep first two tokens
    surf2cui = {}
    with io.open(dict_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 2:
                continue
            surface, cui = parts[0], parts[1]
            surf2cui.setdefault(surface.lower(), cui)
    # also create a list of multiword surfaces (longer first) for better matching
    surfaces = sorted(surf2cui.keys(), key=lambda s: (-len(s), s))
    return surf2cui, surfaces


def find_head_cui(question, surf2cui, surfaces):
    qlow = question.lower()
    # prefer "drug-like" hints (rough heuristic: biologics -mab/-cept and common drug tokens)
    drugish = re.compile(
        r"(mab\b|cept\b|zumab\b|ximab\b|imab\b|umab\b|\bdrug\b|\btherapy\b|\btreatment\b)",
        re.I,
    )
    best = None
    for s in surfaces:
        if s in qlow:
            cui = surf2cui[s]
            best = (s, cui)
            # small bias: if looks drug-ish, stop early
            if drugish.search(question):
                break
    return best[1] if best else None


def main():
    if len(sys.argv) != 4:
        sys.stderr.write(
            "Usage: python prep_autoparse_hints.py <in_jsonl> <dict_txt> <out_jsonl>\n"
        )
        sys.exit(2)
    in_path, dict_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    # ensure parent exists and out_path is a file, not a folder
    parent = os.path.dirname(out_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    if os.path.isdir(out_path):
        raise SystemExit(f"Refusing to overwrite directory as file: {out_path}")

    surf2cui, surfaces = load_dict(dict_path)

    n_in, n_out, n_head = 0, 0, 0
    with io.open(in_path, "r", encoding="utf-8") as fin, io.open(
        out_path, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            n_in += 1
            obj = json.loads(line)
            q = obj.get("question") or obj.get("text") or ""
            rel = infer_relation(q)
            head_cui = find_head_cui(q, surf2cui, surfaces)
            if head_cui:
                n_head += 1

            # write hinted record; preserve qid/question/text
            obj_out = {
                "qid": obj.get("qid"),
                "question": obj.get("question"),
                "text": obj.get("text", obj.get("question")),
                "relations": [rel],
            }
            if head_cui:
                obj_out["head_cui"] = head_cui

            fout.write(json.dumps(obj_out, ensure_ascii=False) + "\n")
            n_out += 1

    sys.stdout.write(f"[prep] read={n_in} wrote={n_out} with_head={n_head}\n")


if __name__ == "__main__":
    main()
