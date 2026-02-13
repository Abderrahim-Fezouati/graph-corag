# -*- coding: utf-8 -*-
"""
Hybrid analysis pipeline:
- Retrieval (BM25)
- Passage-level NER (external env, on retrieved passages only)
- Entity Linking (relation-aware)
- Claim construction
- KG validation

Designed for Graph-CORAG (Windows / PowerShell).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from collections import Counter
from collections import defaultdict
from datetime import datetime

# -----------------------------
# Internal imports (MATCH TREE)
# -----------------------------
from graphcorag.text_retriever import TextRetriever
from analyzer.entity_linking_adapter import ELAdapter
from analyzer.relation_classifier import RelationClassifier
from kg_validation.kg_loader import KGLoader
from kg_validation.kg_validator import KGValidator
from passage_processing.claim_builder import build_claims, infer_predicate


# -----------------------------
# IO helpers
# -----------------------------
def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def normalize_mention(text: str) -> str:
    if not text:
        return ""
    return " ".join(str(text).strip().split()).lower()


def valid_mention(text: str) -> bool:
    s = normalize_mention(text)
    if len(s) < 3:
        return False
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return False
    return True


def parse_query_ner_models(models_arg: str):
    if not models_arg or not models_arg.strip():
        return ["en_core_sci_md", "en_ner_bc5cdr_md", "en_ner_jnlpba_md"]
    models = [m.strip() for m in models_arg.split(",") if m.strip()]
    return list(dict.fromkeys(models))


def merge_mentions_union(*mentions_maps):
    merged = defaultdict(list)
    seen = defaultdict(set)
    for mm in mentions_maps:
        for qid, mentions in mm.items():
            for m in mentions:
                if not valid_mention(m):
                    continue
                key = normalize_mention(m)
                if key in seen[qid]:
                    continue
                seen[qid].add(key)
                merged[qid].append(m)
    return dict(merged)


def validate_ner_runtime(ner_python: str, models: list):
    base_cmd = [
        ner_python,
        "-c",
        "import sys, spacy; print(sys.executable)",
    ]
    try:
        subprocess.run(base_cmd, check=True, capture_output=True, text=True)
    except Exception as exc:
        raise RuntimeError(
            f"NER runtime check failed for '{ner_python}'. "
            "Ensure this Python has spaCy installed."
        ) from exc

    for model in models:
        load_cmd = [
            ner_python,
            "-c",
            f"import spacy; spacy.load({model!r}); print('ok {model}')",
        ]
        try:
            subprocess.run(load_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or str(exc)
            raise RuntimeError(
                f"Failed to load spaCy model '{model}' via '{ner_python}'. "
                f"Install it in that environment. Detail: {detail}"
            ) from exc


# -----------------------------
# Passage-level NER (external)
# -----------------------------
def run_passage_ner(
    corpus_path: str,
    doc_ids: list,
    out_path: Path,
    ner_python: str,
):
    """
    Run spaCy BC5CDR NER ONLY on retrieved passages.
    Output schema per line:
      {
        qid,
        text,
        ents: [{text, label, start, end}]
      }
    """
    tmp_subset = out_path.parent / "tmp_passages.jsonl"

    with open(tmp_subset, "w", encoding="utf-8") as out:
        for row in load_jsonl(corpus_path):
            if row.get("id") in doc_ids:
                out.write(json.dumps(row) + "\n")

    cmd = [
        ner_python,
        "scripts/run_ner_offline.py",
        "--input", str(tmp_subset),
        "--output", str(out_path),
    ]

    print(f"[INFO] Passage NER START qid={out_path.stem} out={out_path}", flush=True)
    print(f"[INFO] Passage NER CMD: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, timeout=600)
    print(f"[INFO] Passage NER END qid={out_path.stem} out={out_path}", flush=True)




# -----------------------------
# Query-level head grounding
# -----------------------------
def sanitize_model_tag(model: str) -> str:
    """
    Normalize model identifier into a filesystem-safe tag.
    """
    if not model:
        return "unknown_model"
    return "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in model)


def run_query_ner(
    queries: list,
    out_dir: Path,
    ner_python: str,
    model: str,
):
    """
    Run spaCy NER over query texts to extract head candidates.
    Returns: (mentions_by_qid, output_path)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    model_tag = sanitize_model_tag(model)
    tmp_input = out_dir / f"query_ner.{model_tag}.input.jsonl"
    tmp_output = out_dir / f"query_ner.{model_tag}.output.jsonl"

    with open(tmp_input, "w", encoding="utf-8") as out:
        for q in queries:
            out.write(json.dumps({
                "id": q["qid"],
                "text": q["text"],
            }) + "\n")

    cmd = [
        ner_python,
        "scripts/run_ner_offline.py",
        "--input", str(tmp_input),
        "--output", str(tmp_output),
        "--model", model,
    ]

    print(f"[INFO] Running query-level NER (model={model})...")
    subprocess.run(cmd, check=True)

    mentions_by_qid = {}
    for row in load_jsonl(tmp_output):
        qid = row.get("id") or row.get("doc_id")
        ents = row.get("ents", [])
        mentions = [e.get("text") for e in ents if e.get("text")]
        mentions_by_qid[qid] = mentions

    return mentions_by_qid, tmp_output


def pick_best_head_candidate(linked_groups: list, min_score: float):
    """
    Select the single best head candidate across mentions (deterministic).
    """
    best = None
    for cands in linked_groups:
        if not cands:
            continue
        cand = cands[0]
        if best is None or float(cand.get("score", 0.0)) > float(best.get("score", 0.0)):
            best = cand
    if best and float(best.get("score", 0.0)) >= float(min_score):
        return best
    return None


def get_installed_spacy_models(ner_python: str) -> list:
    cmd = [
        ner_python,
        "-c",
        "import json; from spacy.util import get_installed_models; print(json.dumps(sorted(get_installed_models())))",
    ]
    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return json.loads(res.stdout.strip() or "[]")
    except Exception as exc:
        print(f"[WARN] Could not list spaCy models via {ner_python}: {exc}")
        return []


def resolve_query_ner_model(requested: str, ner_python: str) -> str:
    if not requested:
        return requested
    if Path(requested).exists():
        return requested

    installed = get_installed_spacy_models(ner_python)
    if requested in installed:
        return requested

    for cand in ["en_core_sci_lg", "en_core_sci_md", "en_core_sci_sm"]:
        if cand in installed:
            print(f"[WARN] Query NER model '{requested}' not found; falling back to '{cand}'.")
            return cand

    if "en_ner_bc5cdr_md" in installed:
        print(
            f"[WARN] Query NER model '{requested}' not found; "
            "falling back to 'en_ner_bc5cdr_md'."
        )
        return "en_ner_bc5cdr_md"

    if installed:
        print(f"[WARN] Query NER model '{requested}' not found; installed models: {installed}")

    return requested

# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--kg", required=True)
    ap.add_argument("--kg_version", required=True)
    ap.add_argument("--retrieval_topk", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--query_ner_model",
        default="en_core_sci_lg",
        help="spaCy model for query-level NER",
    )
    ap.add_argument(
        "--query_ner_mode",
        default="single",
        choices=["single", "ensemble3"],
        help="Query-level NER mode (single is default)",
    )
    ap.add_argument(
        "--query_ner_models",
        default=None,
        help="Comma-separated spaCy models for ensemble3 query NER.",
    )
    ap.add_argument(
        "--query_mode",
        default="free",
        choices=["free", "kg_aligned"],
        help="Query mode (free uses passage tails; kg_aligned uses KG neighbors)",
    )
    ap.add_argument(
        "--query_ner_run_id",
        default=None,
        help="Optional run identifier for query-level NER logging",
    )
    ap.add_argument(
        "--head_min_score",
        type=float,
        default=0.65,
        help="Minimum SapBERT score to accept a head candidate",
    )
    ap.add_argument(
        "--ner_python",
        default=sys.executable,
        help="Python executable of NER environment (default: current)",
    )
    args = ap.parse_args()
    print(f"[INFO] Analyzer python: {sys.executable}")
    print(f"[INFO] NER subprocess python: {args.ner_python}")
    validate_ner_runtime(args.ner_python, [])

    print("[INFO] Loading queries...")
    queries = list(load_jsonl(args.queries))

    print("[INFO] Initializing retriever...")
    retriever = TextRetriever(args.corpus)

    print("[INFO] Initializing EL + relation classifier...")
    el = ELAdapter()
    rel_clf = RelationClassifier()

    print("[INFO] Loading KG once...")
    kg = KGLoader(args.kg)
    validator = KGValidator(kg, args.kg_version)
    kg_predicates = {r.upper() for _, r, _ in getattr(kg, "edge_set", set())}

    outputs = []
    head_debug_rows = []
    skip_reason_counts = Counter()

    missing_head_queries = [q for q in queries if not q.get("head_cui")]
    mentions_by_qid = {}
    mentions_by_model = {}
    query_ner_models = []
    query_ner_path = None
    query_ner_mode = args.query_ner_mode
    query_mode = args.query_mode
    query_ner_run_id = args.query_ner_run_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    resolved_query_ner_model = args.query_ner_model
    if missing_head_queries:
        if query_ner_mode == "ensemble3":
            query_ner_models = parse_query_ner_models(args.query_ner_models)
            validate_ner_runtime(args.ner_python, query_ner_models)
            output_paths = []
            per_model_maps = []
            for model_name in query_ner_models:
                mm, out_path = run_query_ner(
                    queries=missing_head_queries,
                    out_dir=Path(".tmp"),
                    ner_python=args.ner_python,
                    model=model_name,
                )
                mentions_by_model[model_name] = mm
                per_model_maps.append(mm)
                output_paths.append(str(out_path))
            mentions_by_qid = merge_mentions_union(*per_model_maps)
            resolved_query_ner_model = ",".join(query_ner_models)
            query_ner_path = ",".join(output_paths)
        else:
            resolved_query_ner_model = resolve_query_ner_model(
                args.query_ner_model,
                args.ner_python,
            )
            validate_ner_runtime(args.ner_python, [resolved_query_ner_model])
            mentions_by_qid, query_ner_path = run_query_ner(
                queries=missing_head_queries,
                out_dir=Path(".tmp"),
                ner_python=args.ner_python,
                model=resolved_query_ner_model,
            )
            query_ner_models = [resolved_query_ner_model]
            mentions_by_model[resolved_query_ner_model] = mentions_by_qid
        print(f"[INFO] Query-level NER output: {query_ner_path}")
        print(f"[INFO] Query-level NER models: {query_ner_models}")

    for q in queries:
        qid = q["qid"]
        question = q["text"]
        head_cui = q.get("head_cui")
        head_text = None
        head_score = None
        head_source = "query_json" if head_cui else "query_ner"
        ungrounded_head = False
        query_mentions = mentions_by_qid.get(qid, [])
        mentions_for_qid_by_model = {
            model_name: mentions_by_model.get(model_name, {}).get(qid, [])
            for model_name in query_ner_models
        }

        # -------------------------
        # 0) Predict relation (query-level)
        # -------------------------
        relation = None
        if query_mode == "kg_aligned":
            relation = q.get("relation") or q.get("predicate")
            if relation:
                relation = str(relation).strip().upper()
            if not relation:
                relation = infer_predicate(question)
            if not relation:
                relation = rel_clf.predict(question)
        else:
            relation = rel_clf.predict(question)
        if not relation:
            relation = "ASSOCIATED_WITH"
        relation = str(relation).strip().upper()
        relation_in_kg = relation in kg_predicates

        # -------------------------
        # 0b) Head grounding (query-level)
        # -------------------------
        if not head_cui:
            linked_groups = el.link_mentions(
                question=question,
                mentions=query_mentions,
                relation=relation,
                slot="head",
            ) if query_mentions else []
            missing_entity_type_count = sum(
                1
                for cands in linked_groups
                for cand in cands
                if cand.get("entity_type") is None
            )

            best = pick_best_head_candidate(
                linked_groups=linked_groups,
                min_score=args.head_min_score,
            )
            if best:
                head_cui = best.get("kg_id")
                head_text = best.get("surface")
                head_score = best.get("score")
            else:
                ungrounded_head = True

            head_debug_rows.append({
                "qid": qid,
                "text": question,
                "mentions": query_mentions,
                "mentions_by_model": mentions_for_qid_by_model,
                "query_ner_models": query_ner_models,
                "head_cui": head_cui,
                "head_text": head_text,
                "head_score": head_score,
                "head_entity_type": (best or {}).get("entity_type"),
                "head_entity_type_missing": bool(best) and not (best or {}).get("entity_type"),
                "missing_entity_type_count": missing_entity_type_count,
                "head_source": head_source,
                "query_ner_model": resolved_query_ner_model,
                "query_ner_mode": query_ner_mode,
                "query_ner_run_id": query_ner_run_id,
                "ner_python": args.ner_python,
                "head_min_score": args.head_min_score,
                "ungrounded_head": ungrounded_head,
            })

        if ungrounded_head:
            outputs.append({
                "qid": qid,
                "text": question,
                "retrieved_docs": [],
                "predicted_relation": relation,
                "relation_in_kg": relation_in_kg,
                "head_cui": head_cui,
                "head_text": head_text,
                "head_score": head_score,
                "head_source": head_source,
                "ungrounded_head": True,
                "mentions": query_mentions,
                "mentions_by_model": mentions_for_qid_by_model,
                "query_ner_models": query_ner_models,
                "ner_python": args.ner_python,
                "claims": [],
                "kg_validation": [],
                "kg_validation_summary": {},
            })
            continue

        if query_mode == "kg_aligned":
            if not relation_in_kg:
                skip_reason_counts["relation_not_in_kg"] += 1
                outputs.append({
                    "qid": qid,
                    "text": question,
                    "retrieved_docs": [],
                    "predicted_relation": relation,
                    "relation_in_kg": False,
                    "skipped_reason": "relation_not_in_kg",
                    "head_cui": head_cui,
                    "head_text": head_text,
                    "head_score": head_score,
                    "head_source": head_source,
                    "ungrounded_head": False,
                    "mentions": query_mentions,
                    "mentions_by_model": mentions_for_qid_by_model,
                    "query_ner_models": query_ner_models,
                    "ner_python": args.ner_python,
                    "claims": [],
                    "kg_validation": [],
                    "kg_validation_summary": {},
                })
                continue

            tails = kg.tails(head_cui, relation)
            if not tails:
                skip_reason_counts["no_kg_neighbors"] += 1
                outputs.append({
                    "qid": qid,
                    "text": question,
                    "retrieved_docs": [],
                    "predicted_relation": relation,
                    "relation_in_kg": True,
                    "skipped_reason": "no_kg_neighbors",
                    "head_cui": head_cui,
                    "head_text": head_text,
                    "head_score": head_score,
                    "head_source": head_source,
                    "ungrounded_head": False,
                    "mentions": query_mentions,
                    "mentions_by_model": mentions_for_qid_by_model,
                    "query_ner_models": query_ner_models,
                    "ner_python": args.ner_python,
                    "claims": [],
                    "kg_validation": [],
                    "kg_validation_summary": {},
                })
                continue

            claims = []
            for tail in tails:
                if not tail or tail == head_cui:
                    continue
                claims.append({
                    "head_cui": head_cui,
                    "predicate": relation,
                    "tail_cui": tail,
                    "evidence_text": "",
                    "claim_strength": "HYPOTHESIS",
                    "claim_source": "KG",
                })

            validations = []
            summary = Counter()
            for c in claims:
                res = validator.validate_claim(
                    head_cui=c["head_cui"],
                    predicate=c["predicate"],
                    tail_cui=c["tail_cui"],
                    claim_strength=c.get("claim_strength", "HYPOTHESIS"),
                )
                validations.append(res)
                summary[res["verdict"].value] += 1

            outputs.append({
                "qid": qid,
                "text": question,
                "retrieved_docs": [],
                "predicted_relation": relation,
                "relation_in_kg": True,
                "head_cui": head_cui,
                "head_text": head_text,
                "head_score": head_score,
                "head_source": head_source,
                "ungrounded_head": False,
                "mentions": query_mentions,
                "mentions_by_model": mentions_for_qid_by_model,
                "query_ner_models": query_ner_models,
                "ner_python": args.ner_python,
                "claims": claims,
                "kg_validation": validations,
                "kg_validation_summary": dict(summary),
            })
            continue

        # -------------------------
        # 1) Retrieval
        # -------------------------
        retrieved = retriever.retrieve(question, topk=args.retrieval_topk)
        doc_ids = [doc_id for doc_id, _ in retrieved]

        # -------------------------
        # 2) Passage-level NER
        # -------------------------
        passage_ner_path = Path(".tmp") / f"{qid}.passage_ner.jsonl"
        run_passage_ner(
            corpus_path=args.corpus,
            doc_ids=doc_ids,
            out_path=passage_ner_path,
            ner_python=args.ner_python,
        )
        print("[DEBUG] finished passage-level NER loop", flush=True)

        # -------------------------
        # 4) Build passage objects
        # -------------------------
        passages = []

        for row in load_jsonl(passage_ner_path):
            tail_mentions = [e["text"] for e in row.get("ents", [])]
            if not tail_mentions:
                continue

            linked_groups = el.link_mentions(
                question=question,
                mentions=tail_mentions,
                relation=relation,
                slot="tail",
            )

            linked = []
            for cands in linked_groups:
                if cands:
                    linked.append(cands[0])  # best candidate only

            if not linked:
                continue

            passages.append({
                "text": row["text"],
                "linked_entities": linked,
            })

        if not relation_in_kg:
            skip_reason_counts["relation_not_in_kg"] += 1
            outputs.append({
                "qid": qid,
                "text": question,
                "retrieved_docs": doc_ids,
                "predicted_relation": relation,
                "relation_in_kg": False,
                "skipped_reason": "relation_not_in_kg",
                "head_cui": head_cui,
                "head_text": head_text,
                "head_score": head_score,
                "head_source": head_source,
                "ungrounded_head": False,
                "mentions": query_mentions,
                "mentions_by_model": mentions_for_qid_by_model,
                "query_ner_models": query_ner_models,
                "ner_python": args.ner_python,
                "claims": [],
                "kg_validation": [],
                "kg_validation_summary": {},
            })
            continue

        # -------------------------
        # 5) Claim construction
        # -------------------------
        claims = build_claims(
            passages=passages,
            head_cui=head_cui,
            relation=relation,
        )

        # -------------------------
        # 6) KG validation
        # -------------------------
        validations = []
        summary = Counter()

        for c in claims:
            res = validator.validate_claim(
                head_cui=c["head_cui"],
                predicate=c["predicate"],
                tail_cui=c["tail_cui"],
                claim_strength=c.get("claim_strength", "HYPOTHESIS"),
            )
            validations.append(res)
            summary[res["verdict"].value] += 1

        outputs.append({
            "qid": qid,
            "text": question,
            "retrieved_docs": doc_ids,
            "predicted_relation": relation,
            "relation_in_kg": True,
            "head_cui": head_cui,
            "head_text": head_text,
            "head_score": head_score,
            "head_source": head_source,
            "ungrounded_head": False,
            "mentions": query_mentions,
            "mentions_by_model": mentions_for_qid_by_model,
            "query_ner_models": query_ner_models,
            "ner_python": args.ner_python,
            "claims": claims,
            "kg_validation": validations,
            "kg_validation_summary": dict(summary),
        })

    print(f"[DEBUG] about to write outputs n={len(outputs)} to {args.out}", flush=True)
    write_jsonl(args.out, outputs)
    if head_debug_rows:
        head_debug_path = Path(".tmp") / f"query_head_grounding.{query_ner_mode}.{query_ner_run_id}.jsonl"
        write_jsonl(head_debug_path, head_debug_rows)
        print(f"[INFO] Head grounding log: {head_debug_path}")
    if skip_reason_counts:
        print(f"[INFO] Skip summary: {dict(skip_reason_counts)}")
    print(f"[SUCCESS] Wrote output -> {args.out}")


if __name__ == "__main__":
    main()
