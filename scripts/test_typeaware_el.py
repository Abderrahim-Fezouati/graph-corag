from src.analyzer.entity_linking_adapter import ELAdapter

adapter = ELAdapter(
    index_root=r"F:\graph-corag-clean\artifacts\concept_index",
    sapbert_model="cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
    ctx_model=None,  # keep None for now to avoid torch>=2.6 requirement
)


def run(q, head_m, tail_m, rel, intent):
    head = adapter.pick_best_cuis(q, head_m, intent, rel, slot="head")
    tail = adapter.pick_best_cuis(q, tail_m, intent, rel, slot="tail")
    print({"intent": intent, "rel": rel, "q": q, "head": head, "tail": tail})


# INTERACTS_WITH: drug ↔ protein
run(
    "Does adalimumab interact with CD274 protein?",
    ["adalimumab"],
    ["cd274"],
    "INTERACTS_WITH",
    "yesno",
)

# ADVERSE_EFFECT: drug → disease
run(
    "What adverse effect is associated with etanercept?",
    ["etanercept"],
    [],
    "ADVERSE_EFFECT",
    "factoid",
)

# INTERACTS_WITH: protein list (head is protein)
run("Which drugs interact with CTLA4 protein?", ["ctla4"], [], "INTERACTS_WITH", "list")
