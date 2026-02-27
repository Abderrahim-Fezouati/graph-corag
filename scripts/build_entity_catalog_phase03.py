import csv
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
import string as py_string

# ===============================
# Paths
# ===============================
KG_NODES = "data/processed/kg_nodes.canonical.csv"
DRUG_SUBTYPES = "data/processed/kg_drug_subtypes.csv"

RXNCONSO = "data/new data/RxNorm_full_12012025/rrf/RXNCONSO.RRF"
DRUGBANK_XML = "data/new data/drugbank.xml/drugbank.xml"
MESH_XML = "data/new data/mesh/desc2025.xml"

OUTPUT_JSONL = "data/processed/entities/entity_catalog.cleaned.jsonl"


# ===============================
# Normalization & Surface Expansion
# ===============================
def normalize(text: str) -> str:
    """Lowercase and collapse whitespace."""
    return re.sub(r"\s+", " ", text.lower().strip())


def remove_punct(text: str) -> str:
    return text.translate(str.maketrans("", "", py_string.punctuation))


def hyphen_space_variants(text: str) -> set:
    variants = set()
    base = text.replace("-", " ")
    base = re.sub(r"\s+", " ", base)
    variants.add(base)
    variants.add(base.replace(" ", "-"))
    return variants


def disease_word_order_variants(text: str) -> set:
    tokens = text.split()
    variants = set()
    if len(tokens) == 2:
        variants.add(" ".join(reversed(tokens)))
    return variants


def expand_surfaces(text: str, entity_type: str = None) -> set:
    """Deterministic surface expansion."""
    norm = normalize(text)
    surfaces = set()

    surfaces.add(norm)

    no_punct = remove_punct(norm)
    surfaces.add(no_punct)

    for v in list(surfaces):
        surfaces.update(hyphen_space_variants(v))

    if entity_type == "disease":
        for v in list(surfaces):
            surfaces.update(disease_word_order_variants(v))

    return {s.strip() for s in surfaces if s.strip()}


# ===============================
# Load canonical KG nodes
# ===============================
kg_nodes = {}
with open(KG_NODES, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        kg_nodes[row["kg_id"]] = {
            "kg_id": row["kg_id"],
            "entity_type": row["entity_type"],
            "canonical_name": row["canonical_name"],
            "synonyms": {row["canonical_name"]},
            "sources": set(),
        }

# ===============================
# Load drug subtypes
# ===============================
drug_subtype = {}
with open(DRUG_SUBTYPES, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        drug_subtype[row["kg_id"]] = row["drug_subtype"]

# ===============================
# Build expanded surface → kg_id map
# ===============================
surface_to_kg = defaultdict(set)
for kg_id, node in kg_nodes.items():
    for surf in expand_surfaces(node["canonical_name"], node["entity_type"]):
        surface_to_kg[surf].add(kg_id)

# ===============================
# Collect candidate synonyms
# surface → source → names
# ===============================
surface_candidates = defaultdict(lambda: defaultdict(set))

# ---------- RxNorm ----------
with open(RXNCONSO, encoding="utf-8") as f:
    for line in f:
        fields = line.rstrip("\n").split("|")
        if len(fields) < 15:
            continue

        sab = fields[11]
        tty = fields[12]
        rxn_str = fields[14]

        if sab != "RXNORM":
            continue
        if tty not in {"IN", "BN", "PIN"}:
            continue

        for surf in expand_surfaces(rxn_str):
            surface_candidates[surf]["RxNorm"].add(rxn_str)

# ---------- DrugBank ----------
tree = ET.parse(DRUGBANK_XML)
root = tree.getroot()
ns = {"db": "http://www.drugbank.ca"}

for drug in root.findall("db:drug", ns):
    names = set()

    main_name = drug.findtext("db:name", default="", namespaces=ns)
    if main_name:
        names.add(main_name)

    for brand in drug.findall("db:brands/db:brand", ns):
        if brand.text:
            names.add(brand.text)

    for syn in drug.findall("db:synonyms/db:synonym", ns):
        if syn.text:
            names.add(syn.text)

    for name in names:
        for surf in expand_surfaces(name):
            surface_candidates[surf]["DrugBank"].add(name)

# ---------- MeSH ----------
tree = ET.parse(MESH_XML)
root = tree.getroot()

for desc in root.findall("DescriptorRecord"):
    terms = set()

    dn = desc.findtext("DescriptorName/String", default="")
    if dn:
        terms.add(dn)

    for term in desc.findall("ConceptList/Concept/TermList/Term/String"):
        if term.text:
            terms.add(term.text)

    for t in terms:
        for surf in expand_surfaces(t, entity_type="disease"):
            surface_candidates[surf]["MeSH"].add(t)

# ===============================
# Attach synonyms with STRICT rules
# ===============================
discarded_ambiguous = 0

for surface, src_map in surface_candidates.items():
    kg_ids = surface_to_kg.get(surface)

    if not kg_ids:
        continue

    if len(kg_ids) != 1:
        discarded_ambiguous += 1
        continue

    kg_id = next(iter(kg_ids))
    node = kg_nodes[kg_id]

    for src, names in src_map.items():

        if src == "RxNorm":
            if node["entity_type"] != "drug":
                continue
            if drug_subtype.get(kg_id) not in {"small_molecule", "biologic", "vaccine"}:
                continue

        if src == "DrugBank":
            if node["entity_type"] != "drug":
                continue
            if drug_subtype.get(kg_id) not in {"small_molecule", "biologic"}:
                continue

        if src == "MeSH":
            if node["entity_type"] != "disease":
                continue

        node["synonyms"].update(names)
        node["sources"].add(src)

# ===============================
# Write entity catalog
# ===============================
os.makedirs(os.path.dirname(OUTPUT_JSONL), exist_ok=True)

syn_counts = []
with open(OUTPUT_JSONL, "w", encoding="utf-8") as out:
    for node in kg_nodes.values():
        syns = sorted(set(node["synonyms"]))
        syn_counts.append(len(syns))
        out.write(
            json.dumps(
                {
                    "kg_id": node["kg_id"],
                    "entity_type": node["entity_type"],
                    "canonical_name": node["canonical_name"],
                    "synonyms": syns,
                    "sources": sorted(node["sources"]),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

# ===============================
# Reporting
# ===============================
print(f"Total entities: {len(kg_nodes)}")
print(f"Avg synonyms per entity: {sum(syn_counts)/len(syn_counts):.2f}")
print(f"Max synonyms for any entity: {max(syn_counts)}")
print(f"Discarded ambiguous surfaces: {discarded_ambiguous}")
