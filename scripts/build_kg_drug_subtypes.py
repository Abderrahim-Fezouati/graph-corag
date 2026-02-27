import csv
import re
from collections import Counter

INPUT_CSV = "data/processed/kg_nodes.canonical.csv"
OUTPUT_CSV = "data/processed/kg_drug_subtypes.csv"


def classify_drug(canonical_name):
    name = canonical_name.lower()
    # 1. Vaccine
    if "vaccine" in name or "toxoid" in name:
        return "vaccine"
    # 2. Biologic (suffix-based)
    if name.endswith("mab") or name.endswith("zumab"):
        return "biologic"
    if any(
        x in name
        for x in [
            "antibody",
            "cell therapy",
            "gene therapy",
            "interleukin",
            "fusion protein",
            "peg",
            "recombinant",
            "immunoglobulin",
        ]
    ):
        return "biologic"
    # 3. Enzyme/protein (word-boundary regex for 'ase')
    if re.search(r"\\b\\w+ase\\b", name) or any(
        x in name
        for x in [
            "enzyme",
            "protein",
            "kinase",
            "hormone",
            "factor",
            "peptide",
            "interferon",
            "insulin",
            "growth factor",
        ]
    ):
        return "enzyme/protein"
    # 4. Category/combination
    if any(
        x in name
        for x in ["combination", "class", "group", "category", "agent", "preparation"]
    ):
        return "category"
    # 5. Default: small molecule
    return "small_molecule"


subtype_counts = Counter()

with open(INPUT_CSV, newline="", encoding="utf-8") as infile, open(
    OUTPUT_CSV, "w", newline="", encoding="utf-8"
) as outfile:
    reader = csv.DictReader(infile)
    writer = csv.writer(outfile)
    writer.writerow(["kg_id", "drug_subtype"])
    for row in reader:
        if row["entity_type"] == "drug":
            subtype = classify_drug(row["canonical_name"])
            writer.writerow([row["kg_id"], subtype])
            subtype_counts[subtype] += 1

# Report subtype distribution
for subtype, count in subtype_counts.items():
    print(f"{subtype}: {count}")
