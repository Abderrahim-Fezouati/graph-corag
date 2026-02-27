import csv, io, json, os, random, re, sys

NEW = sys.argv[1]
random.seed(42)

kg_csv = os.path.join(NEW, "data", "kg_edges.2hop.csv")
overlay_path = os.path.join(NEW, "config", "umls_dict.overlay.json")
out_path = os.path.join(NEW, "out", "queries.paraphrase.bioask100.jsonl")


def load_overlay(p):
    try:
        return json.load(io.open(p, "r", encoding="utf-8"))
    except Exception:
        return {}


def pick_surface(eid, overlay):
    ss = overlay.get(eid) or []
    if not ss:
        core = re.sub(
            r"^(drug|disease|class|symptom|gene|protein)_", "", eid, flags=re.I
        )
        ss = [core.replace("_", " ")]
    # prefer longer, more specific surface occasionally
    ss_sorted = sorted(ss, key=len, reverse=True)
    return random.choice(
        ss_sorted[: min(len(ss_sorted), 3)] if len(ss_sorted) >= 3 else ss_sorted
    )


# Light naturalization helpers
def cap(txt):  # capitalize drug/disease names nicely
    return re.sub(r"\b([a-z])", lambda m: m.group(1).upper(), txt, count=1)


POP_CTX = [
    "in adult patients",
    "in elderly populations",
    "in pediatric cases",
    "among oncology patients",
    "in clinical settings",
    "in routine practice",
]
EVID_CTX = [
    "according to published studies",
    "based on clinical observations",
    "as reported in the literature",
    "in randomized trials",
    "per case reports",
    "per pharmacovigilance data",
]
COADMIN_CTX = [
    "during co-administration",
    "when used together",
    "during concurrent therapy",
    "under combination treatment",
]

TEMPL_IW = [
    "Do {H} and {T} interact {X}?",
    "Is there evidence of a pharmacologic interaction between {H} and {T} {Y}?",
    "Does {H} affect the action of {T} {Y}?",
    "Are interactions reported when {H} and {T} are used together {Y}?",
    "Is co-administration of {H} with {T} associated with an interaction {Y}?",
    "What is known about the interaction between {H} and {T} {Y}?",
]
TEMPL_AE = [
    "Is {T} reported as an adverse event of {H} therapy {Y}?",
    "Can treatment with {H} lead to {T} as a side effect {Y}?",
    "Is {T} associated with exposure to {H} {Y}?",
    "Has {T} been observed during {H} treatment {Y}?",
    "Do reports describe {T} in patients receiving {H} {Y}?",
    "Is {T} documented in relation to {H} use {Y}?",
]

overlay = load_overlay(overlay_path)

# Load KG edges, keep only fully-specified ones (non-empty head/tail)
IW, AE = [], []
with io.open(kg_csv, "r", encoding="utf-8", errors="ignore") as f:
    for row in csv.reader(f):
        if len(row) < 3:
            continue
        h, r, t = row[0].strip(), row[1].strip(), row[2].strip()
        if not (h and r and t):
            continue
        if r == "INTERACTS_WITH":
            IW.append((h, t))
        elif r == "ADVERSE_EFFECT":
            AE.append((h, t))

random.shuffle(IW)
random.shuffle(AE)
IW = IW[:60]  # sample a bit extra to dedup later
AE = AE[:60]


def make_iw_q(h, t):
    Hs, Ts = cap(pick_surface(h, overlay)), cap(pick_surface(t, overlay))
    Y = random.choice(
        [
            "",
            random.choice(EVID_CTX),
            random.choice(COADMIN_CTX),
            random.choice(POP_CTX),
        ]
    ).strip()
    Y = "" if Y == "" else Y
    tpl = random.choice(TEMPL_IW)
    q = tpl.format(H=Hs, T=Ts, X=random.choice(COADMIN_CTX), Y=(" " + Y if Y else ""))
    return {"text": q.strip(), "head": h, "tail1": t, "tail2": ""}


def make_ae_q(h, t):
    Hs, Ts = cap(pick_surface(h, overlay)), cap(pick_surface(t, overlay))
    Y = random.choice(["", random.choice(EVID_CTX), random.choice(POP_CTX)]).strip()
    q = random.choice(TEMPL_AE).format(H=Hs, T=Ts, Y=(" " + Y if Y else ""))
    return {"text": q.strip(), "head": h, "tail1": "", "tail2": t}


# Build 50 unique IW and 50 unique AE questions (avoid duplicate texts)
uniq = set()
out_items = []

for h, t in IW:
    item = make_iw_q(h, t)
    if item["text"] in uniq:
        continue
    uniq.add(item["text"])
    out_items.append(item)
    if len([x for x in out_items if x["tail1"]]) >= 50:
        break

for h, t in AE:
    item = make_ae_q(h, t)
    if item["text"] in uniq:
        continue
    uniq.add(item["text"])
    out_items.append(item)
    if len([x for x in out_items if x["tail2"]]) >= 50:
        break

# If still short (rare), top up with more shuffled edges
if len(out_items) < 100:
    more_IW = IW[50:] + IW
    more_AE = AE[50:] + AE
    for h, t in more_IW:
        if len([x for x in out_items if x["tail1"]]) >= 50:
            break
        item = make_iw_q(h, t)
        if item["text"] in uniq:
            continue
        uniq.add(item["text"])
        out_items.append(item)
    for h, t in more_AE:
        if len([x for x in out_items if x["tail2"]]) >= 50:
            break
        item = make_ae_q(h, t)
        if item["text"] in uniq:
            continue
        uniq.add(item["text"])
        out_items.append(item)

os.makedirs(os.path.join(NEW, "out"), exist_ok=True)
with io.open(out_path, "w", encoding="utf-8") as out:
    for j in out_items[:100]:
        out.write(json.dumps(j, ensure_ascii=False) + "\n")

print(
    "wrote",
    out_path,
    "n=",
    len(out_items[:100]),
    "IW=",
    sum(1 for x in out_items[:100] if x["tail1"]),
    "AE=",
    sum(1 for x in out_items[:100] if x["tail2"]),
)
