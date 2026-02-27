from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

try:
    from .common import (
        ensure_files,
        iter_rrf,
        normalize_surface,
        slugify,
        write_json,
    )
except ImportError:
    from kb.build.common import (
        ensure_files,
        iter_rrf,
        normalize_surface,
        slugify,
        write_json,
    )


DRUG_TUIS = {"T109", "T110", "T116", "T121", "T126", "T129", "T130", "T195", "T200"}
DISEASE_TUIS = {"T047", "T048", "T184", "T191"}
CHEMICAL_TUIS = {"T103", "T104", "T109", "T110", "T111", "T114", "T115", "T116", "T196"}
GENE_TUIS = {"T028", "T085", "T086", "T087", "T088"}


def infer_entity_type(tuis: set[str]) -> str:
    if tuis & DRUG_TUIS:
        return "drug"
    if tuis & DISEASE_TUIS:
        return "disease"
    if tuis & CHEMICAL_TUIS:
        return "chemical"
    if tuis & GENE_TUIS:
        return "gene"
    return "entity"


def kg_id_for(cui: str, canonical: str, entity_type: str) -> str:
    if entity_type in {"drug", "disease", "chemical", "gene"}:
        return f"{entity_type}_{slugify(canonical)}"
    return f"umls_{cui.lower()}"


def _add_synonym(catalog: dict, by_norm: dict, kg_id: str, value: str, source: str) -> bool:
    s = (value or "").strip()
    if len(s) < 2:
        return False
    n = normalize_surface(s)
    if n not in by_norm:
        return False
    hits = by_norm[n]
    if len(hits) != 1:
        return False
    tgt = next(iter(hits))
    if tgt != kg_id:
        return False
    catalog[kg_id]["synonyms"].add(s)
    catalog[kg_id]["sources"].add(source)
    return True


def build(raw_root: Path, out_dir: Path, version: str, progress_every: int = 500000) -> dict:
    um_conso = raw_root / "UMLS" / "MRCONSO.RRF"
    um_sty = raw_root / "UMLS" / "MRSTY.RRF"
    rxn_conso = raw_root / "RxNorm" / "RXNCONSO.RRF"
    mesh_xml = raw_root / "Mesh" / "desc2025.xml"
    drugbank_xml = raw_root / "DrugBank" / "drugbank.xml"
    ensure_files([um_conso, um_sty, rxn_conso, mesh_xml, drugbank_xml])

    out_path = out_dir / "entity_catalog.jsonl"
    report_path = out_dir / "stage_01_report.json"

    cui_tuis: dict[str, set[str]] = defaultdict(set)
    mrsty_rows = 0
    for fields in iter_rrf(um_sty, progress_every=progress_every):
        mrsty_rows += 1
        if len(fields) < 4:
            continue
        cui = fields[0].strip().upper()
        tui = fields[1].strip().upper()
        if cui and tui:
            cui_tuis[cui].add(tui)

    catalog: dict[str, dict] = {}
    cui_to_kg: dict[str, str] = {}
    by_norm_surface: dict[str, set[str]] = defaultdict(set)
    cui_seen = set()
    mrconso_rows = 0
    filtered_non_eng = 0

    for fields in iter_rrf(um_conso, progress_every=progress_every):
        mrconso_rows += 1
        if len(fields) < 15:
            continue
        cui = fields[0].strip().upper()
        lat = fields[1].strip().upper()
        is_pref = fields[6].strip().upper() == "Y"
        text = fields[14].strip()
        if not (cui and text):
            continue
        if lat != "ENG":
            filtered_non_eng += 1
            continue

        etype = infer_entity_type(cui_tuis.get(cui, set()))
        if etype == "entity":
            continue
        if cui not in cui_seen:
            canonical = text
            kg_id = kg_id_for(cui, canonical, etype)
            catalog[kg_id] = {
                "kg_id": kg_id,
                "cui": cui,
                "entity_type": etype,
                "canonical_name": canonical,
                "synonyms": set([canonical]),
                "sources": set(["UMLS"]),
            }
            cui_seen.add(cui)
            cui_to_kg[cui] = kg_id
        else:
            kg_id = cui_to_kg[cui]
            if is_pref:
                catalog[kg_id]["canonical_name"] = text
            catalog[kg_id]["synonyms"].add(text)

    for kg_id, row in catalog.items():
        for s in row["synonyms"]:
            by_norm_surface[normalize_surface(s)].add(kg_id)

    rx_rows = 0
    rx_added = 0
    for fields in iter_rrf(rxn_conso, progress_every=progress_every):
        rx_rows += 1
        if len(fields) < 15:
            continue
        sab = fields[11].strip().upper()
        tty = fields[12].strip().upper()
        text = fields[14].strip()
        if sab != "RXNORM" or tty not in {"IN", "BN", "PIN"}:
            continue
        n = normalize_surface(text)
        for kg_id in by_norm_surface.get(n, set()):
            if catalog[kg_id]["entity_type"] == "drug":
                if _add_synonym(catalog, by_norm_surface, kg_id, text, "RxNorm"):
                    rx_added += 1

    db_added = 0
    ns = {"db": "http://www.drugbank.ca"}
    root = ET.parse(drugbank_xml).getroot()
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
            n = normalize_surface(name)
            for kg_id in by_norm_surface.get(n, set()):
                if catalog[kg_id]["entity_type"] == "drug":
                    if _add_synonym(catalog, by_norm_surface, kg_id, name, "DrugBank"):
                        db_added += 1

    mesh_added = 0
    root = ET.parse(mesh_xml).getroot()
    for desc in root.findall("DescriptorRecord"):
        terms = set()
        dn = desc.findtext("DescriptorName/String", default="")
        if dn:
            terms.add(dn)
        for term in desc.findall("ConceptList/Concept/TermList/Term/String"):
            if term.text:
                terms.add(term.text)
        for t in terms:
            n = normalize_surface(t)
            for kg_id in by_norm_surface.get(n, set()):
                if catalog[kg_id]["entity_type"] == "disease":
                    if _add_synonym(catalog, by_norm_surface, kg_id, t, "MeSH"):
                        mesh_added += 1

    written = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for kg_id in sorted(catalog):
            row = catalog[kg_id]
            payload = {
                "kg_id": row["kg_id"],
                "cui": row["cui"],
                "entity_type": row["entity_type"],
                "canonical_name": row["canonical_name"],
                "synonyms": sorted(set(row["synonyms"])),
                "sources": sorted(set(row["sources"])),
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            written += 1

    report = {
        "stage": "01_build_entity_catalog",
        "version": version,
        "inputs": {
            "MRCONSO": str(um_conso),
            "MRSTY": str(um_sty),
            "RXNCONSO": str(rxn_conso),
            "MeSH_XML": str(mesh_xml),
            "DrugBank_XML": str(drugbank_xml),
        },
        "counts": {
            "mrsty_rows": mrsty_rows,
            "mrconso_rows": mrconso_rows,
            "filtered_non_english": filtered_non_eng,
            "rxnorm_rows": rx_rows,
            "rxnorm_synonyms_added": rx_added,
            "mesh_synonyms_added": mesh_added,
            "drugbank_synonyms_added": db_added,
            "entities_written": written,
        },
        "outputs": {"entity_catalog": str(out_path)},
    }
    write_json(report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw_root", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--progress_every", type=int, default=500000)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    report = build(
        raw_root=Path(args.raw_root),
        out_dir=Path(args.out_dir),
        version=args.version,
        progress_every=args.progress_every,
    )
    print(
        f"[01] wrote {report['outputs']['entity_catalog']} "
        f"({report['counts']['entities_written']} entities)"
    )


if __name__ == "__main__":
    main()
