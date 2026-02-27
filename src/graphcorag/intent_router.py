import re

YESNO_RE = re.compile(r"^(is|does|do|are|can|could|would|whether)\b", re.I)
PRED_CUES = {
    "ADVERSE_EFFECT": [
        r"adverse effect",
        r"side effect",
        r"toxicit",
        r"hepatotox",
        r"nephrotox",
        r"pneumonitis",
    ],
    "INTERACTS_WITH": [
        r"interact",
        r"contraindicat",
        r"co[- ]?admin",
        r"drug[- ]?drug",
        r"increase[s]? levels",
        r"reduce[s]? levels",
    ],
    "INDICATION": [
        r"indicat",
        r"treat[s]?|treatment",
        r"for \b.*\b(cancer|disease|condition|syndrome)",
    ],
}


def detect_predicate(text):
    text_l = text.lower()
    found = []
    for rel, pats in PRED_CUES.items():
        if any(re.search(p, text_l) for p in pats):
            found.append(rel)
    return found


def route_intent(q, extracted_surfaces):
    text = q.strip()
    yn = bool(YESNO_RE.search(text))
    cues = detect_predicate(text)
    ent_count = len(set([s.lower() for s in (extracted_surfaces or [])]))

    if yn and (cues) and ent_count >= 1:
        intent = "yesno"
    elif cues and ent_count >= 1:
        intent = "factoid"
    elif ent_count >= 2:
        intent = "multihop"
    else:
        intent = "multihop"
    return intent, cues
