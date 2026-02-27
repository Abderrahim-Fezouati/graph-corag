import re, json, random
from pathlib import Path

ABBR = [
    (r"\bproton pump inhibitors?\b", "PPIs"),
    (r"\bdirect[- ]acting oral anticoagulants?\b", "DOACs"),
    (r"\bangiotensin[- ]converting enzyme inhibitors?\b", "ACE inhibitors"),
    (r"\bACE inhibitors?\b", "ACEi"),
    (r"\bclostridioides difficile\b", "C. diff"),
    (r"\bmyocardial infarction\b", "MI"),
    (r"\bhuman immunodeficiency virus\b", "HIV"),
]

HEDGE_STARTS = ["Could", "Should", "Would", "Might", "Can"]
NEG_TOKENS = ["not", "never"]


def _abbr(s):
    for pat, rep in ABBR:
        s = re.sub(pat, rep, s, flags=re.I)
    return s


def _first_token_ablation(q):
    parts = q.strip().split()
    return " ".join(parts[1:]) if len(parts) > 1 else q


def _ensure_qmark(s):
    s = s.strip()
    return s if s.endswith("?") else s + "?"


def _prefix_context(q):
    ctxs = [
        "A patient on multiple medications. ",
        "Considering pregnancy status, ",
        "In the setting of chronic kidney disease, ",
        "For hospitalized adults, ",
        "In clinical practice, ",
    ]
    return random.choice(ctxs) + q[0].lower() + q[1:]


def _reorder_clause_list(q):
    # crude reorder around "that/also/and"
    s = q
    s = re.sub(r"^Which\s+", "List ", s, flags=re.I)
    s = re.sub(r"^What\s+", "List ", s, flags=re.I)
    s = re.sub(r"\bthat\b", "which", s, flags=re.I)
    # move tail clause first if present
    m = re.search(r"(that|which)\s+([^?]+)", s, flags=re.I)
    if m:
        s = f"Identify {m.group(2)} among drugs"
    return _ensure_qmark(s)


def _factoid_rephrase(q):
    # Replace "What is/What are" with directive forms
    s = re.sub(r"^\s*what\s+is\s+the\s+", "Explain the ", q, flags=re.I)
    s = re.sub(r"^\s*what\s+is\s+", "Explain ", s, flags=re.I)
    s = re.sub(r"^\s*what\s+are\s+the\s+", "Describe the ", s, flags=re.I)
    s = re.sub(r"^\s*what\s+are\s+", "Describe ", s, flags=re.I)
    # Alternative phrasing
    alts = [
        lambda x: "Provide the mechanism for "
        + re.sub(r"^\s*(explain|describe)\s+(the\s+)?", "", x, flags=re.I),
        lambda x: "Mechanistically, "
        + re.sub(r"^\s*(explain|describe)\s+(the\s+)?", "", x, flags=re.I),
        lambda x: "Summarize "
        + re.sub(r"^\s*(explain|describe)\s+(the\s+)?", "", x, flags=re.I),
    ]
    return random.choice(alts)(s).strip().rstrip(".") + "."


def _yesno_negate(q):
    # Turn "Does X ..." -> "Does X not ... ?"
    s = q.strip()
    if re.match(r"^(does|do|is|are|can|should|could|would)\b", s, flags=re.I):
        parts = s.split(maxsplit=1)
        if len(parts) == 2:
            return _ensure_qmark(parts[0] + " " + NEG_TOKENS[0] + " " + parts[1])
    # fallback
    return _ensure_qmark("Do " + NEG_TOKENS[0] + " " + s.rstrip("?"))


def _yesno_hedge(q):
    s = re.sub(
        r"^(does|do|is|are|can|should|could|would)\b",
        random.choice(HEDGE_STARTS),
        q,
        flags=re.I,
    )
    return _ensure_qmark(s)


def _list_directive(q):
    s = re.sub(
        r"^\s*(which|what|list|name|give|show)\b.*",
        "Provide a list of relevant entities that satisfy the constraints.",
        q,
        flags=re.I,
    )
    return _ensure_qmark(s)


def _make_list_multisentence(q):
    return _ensure_qmark(f"In patients with complex regimens. {q}")


def _transform_yesno(q):
    cands = [
        _abbr(_prefix_context(q)),
        _abbr(_yesno_negate(q)),
        _abbr(_yesno_hedge(q)),
        _abbr(_first_token_ablation(q)),
    ]
    return list(dict.fromkeys([_ensure_qmark(x) for x in cands]))


def _transform_factoid(q):
    cands = [
        _abbr(_factoid_rephrase(q)),
        _abbr("Briefly, " + q[0].lower() + q[1:]),
        _abbr(_first_token_ablation(q)),
    ]
    return list(dict.fromkeys([_ensure_qmark(x) for x in cands]))


def _transform_list(q):
    cands = [
        _abbr(_reorder_clause_list(q)),
        _abbr(_make_list_multisentence(q)),
        _abbr(_list_directive(q)),
        _abbr(_first_token_ablation(q)),
    ]
    return list(dict.fromkeys([_ensure_qmark(x) for x in cands]))


def load_split(p):
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data_dir", required=True, help="folder with train.jsonl/val.jsonl/test.jsonl"
    )
    ap.add_argument("--out_file", required=True, help="path to write hard test JSONL")
    ap.add_argument(
        "--per_class",
        type=int,
        default=30,
        help="number of seeds per class to transform",
    )
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    p = Path(args.data_dir)
    base = []
    for split in ["train", "val", "test"]:
        f = p / f"{split}.jsonl"
        if f.exists():
            base.extend(load_split(f))

    by_label = {"yesno": [], "factoid": [], "list": []}
    for r in base:
        lab = str(r["label"]).lower().strip()
        if lab in by_label:
            by_label[lab].append(r)

    out = []
    for lab, items in by_label.items():
        random.shuffle(items)
        seeds = items[: args.per_class]
        for r in seeds:
            q = r["question"].strip()
            if lab == "yesno":
                variants = _transform_yesno(q)
            elif lab == "factoid":
                variants = _transform_factoid(q)
            else:
                variants = _transform_list(q)
            for i, v in enumerate(variants, 1):
                out.append(
                    {
                        "id": f"HARD_{lab.upper()}_{r.get('id','Q')}_{i}",
                        "question": v,
                        "label": lab,
                    }
                )

    # dedupe by normalized question
    seen = set()
    final = []
    for r in out:
        key = re.sub(
            r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", r["question"].lower())
        ).strip()
        if key not in seen:
            seen.add(key)
            final.append(r)

    with open(args.out_file, "w", encoding="utf-8") as w:
        for r in final:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(final)} examples to {args.out_file}")


if __name__ == "__main__":
    main()
