# -*- coding: utf-8 -*-
import json, re, csv, io, os, sys

# Build a head-node resolver from both: KG nodes and (optionally) dict
# We expect KG ids like "drug_tamoxifen", "drug_fluoxetine" etc.

AE_PAT = re.compile(
    r"(adverse|side[- ]?effect|safety|harm|untoward|complication|toxicit|unfavorable|untoward)",
    re.I,
)
DDI_PAT = re.compile(
    r"(interact|co[- ]?prescrib|contraindicat|avoid(ed)? with|clash|co[- ]?medicat|serotonin syndrome|qt prolong)",
    re.I,
)


def infer_relation(q):
    if DDI_PAT.search(q):
        return "INTERACTS_WITH"
    if AE_PAT.search(q):
        return "ADVERSE_EFFECT"
    # fallback
    return "ADVERSE_EFFECT"


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_kg_heads(kg_path):
    heads = set()
    labels = set()
    with io.open(kg_path, encoding="utf-8", errors="ignore") as f:
        rdr = csv.reader(f)
        # try to sniff header; accept any column order [head,rel,tail]
        for row in rdr:
            if not row or len(row) < 3:
                continue
            h = row[0].strip()
            t = row[2].strip()
            if not h or not t:
                continue
            heads.add(h)
            # also remember a readable surface for matching: strip prefixes and underscores
            lab = h
            lab = re.sub(r"^(drug_|disease_|gene_)", "", lab)
            lab = lab.replace("_", " ")
            labels.add((norm(lab), h))
    # build dict keyed by normalized label -> node id (prefer longer labels later)
    # multiple keys may map to same id; we’ll select first match occurrence in Q
    lab2id = {}
    for nl, hid in sorted(labels, key=lambda x: (-len(x[0]), x[0])):
        if nl:
            lab2id.setdefault(nl, hid)
    return lab2id


def load_dict(dict_path):
    surf2id = {}
    if not dict_path or not os.path.isfile(dict_path):
        return surf2id
    with io.open(dict_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 2:
                continue
            surface, node = parts[0], parts[1]
            surf2id[norm(surface)] = node
    return surf2id


def find_head(question, lab2id, dict2id):
    qn = norm(question)
    # candidate surfaces = contiguous tokens (n-grams) present in q
    tokens = qn.split()
    for n in range(min(6, len(tokens)), 0, -1):  # try longer spans first
        for i in range(0, len(tokens) - n + 1):
            span = " ".join(tokens[i : i + n])
            if span in dict2id:
                return dict2id[span]
            if span in lab2id:
                return lab2id[span]
    return None


def main():
    if len(sys.argv) < 4:
        sys.stderr.write(
            "Usage: python prep_autoparse_hints_v2.py <in_jsonl> <kg_csv> <out_jsonl> [umls_dict.txt]\n"
        )
        sys.exit(2)
    in_path, kg_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    dict_path = sys.argv[4] if len(sys.argv) > 4 else None

    lab2id = load_kg_heads(kg_path)
    dict2id = load_dict(dict_path)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.isdir(out_path):
        raise SystemExit(f"Refusing to overwrite directory: {out_path}")

    n_in = n_out = n_head = 0
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
            head = find_head(q, lab2id, dict2id)

            out = {
                "qid": obj.get("qid"),
                "question": obj.get("question"),
                "text": obj.get("text", obj.get("question")),
                "relations": [rel],
            }
            if head:
                out["head_cui"] = head
                n_head += 1
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            n_out += 1
    print(f"[prep_v2] read={n_in} wrote={n_out} head_cui_found={n_head}")


if __name__ == "__main__":
    main()
