from __future__ import annotations

import argparse
import json
from pathlib import Path

import faiss
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

try:
    from .common import ensure_files, write_json
except ImportError:
    from kb.build.common import ensure_files, write_json


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    denom = np.linalg.norm(x, axis=1, keepdims=True)
    denom = np.clip(denom, a_min=1e-12, a_max=None)
    return x / denom


def _encode(model, tokenizer, texts: list[str], batch_size: int, max_length: int, device: str) -> np.ndarray:
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            enc = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            hid = model(**enc).last_hidden_state[:, 0, :]
            hid = torch.nn.functional.normalize(hid, p=2, dim=1)
            out.append(hid.cpu().numpy())
            print(f"[sapbert] encoded {min(i + len(batch), len(texts)):,}/{len(texts):,}")
    return np.vstack(out) if out else np.zeros((0, 768), dtype=np.float32)


def build(
    raw_root: Path,
    out_dir: Path,
    version: str,
    model_name: str = "models/sapbert",
    batch_size: int = 64,
    max_length: int = 64,
    local_files_only: bool = True,
) -> dict:
    _ = raw_root
    entity_catalog = out_dir / "entity_catalog.jsonl"
    ensure_files([entity_catalog])

    sapbert_root = out_dir / "sapbert_index"
    sapbert_root.mkdir(parents=True, exist_ok=True)
    out_index = sapbert_root / "index.faiss"
    out_rows = sapbert_root / "rows.jsonl"
    report_path = out_dir / "stage_07_report.json"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=local_files_only)
    model = AutoModel.from_pretrained(model_name, local_files_only=local_files_only).to(device)
    model.eval()

    rows = []
    with entity_catalog.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            kg_id = row["kg_id"]
            et = row.get("entity_type", "entity")
            canonical = row.get("canonical_name", "")
            for s in row.get("synonyms", []):
                rows.append(
                    {
                        "kg_id": kg_id,
                        "entity_type": et,
                        "surface": s,
                        "canonical_name": canonical,
                    }
                )
    rows.sort(key=lambda r: (r["entity_type"], r["kg_id"], r["surface"].lower()))
    texts = [r["surface"] for r in rows]
    emb = _encode(model, tokenizer, texts, batch_size=batch_size, max_length=max_length, device=device)
    emb = _l2_normalize(emb.astype(np.float32))

    dim = emb.shape[1] if emb.size else 768
    index = faiss.IndexFlatIP(dim)
    if len(emb):
        index.add(emb)
    faiss.write_index(index, str(out_index))

    with out_rows.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Runtime compatibility sub-indexes expected by current SapBERTLinkerV2
    for etype in ("Drug", "Disease"):
        sub_rows = [r for r in rows if r["entity_type"].lower() == etype.lower()]
        texts = [r["surface"] for r in sub_rows]
        sub_emb = _encode(model, tokenizer, texts, batch_size=batch_size, max_length=max_length, device=device)
        sub_emb = _l2_normalize(sub_emb.astype(np.float32)) if len(sub_emb) else np.zeros((0, dim), dtype=np.float32)
        sub_dir = sapbert_root / etype
        sub_dir.mkdir(parents=True, exist_ok=True)
        sub_index = faiss.IndexFlatIP(dim)
        if len(sub_emb):
            sub_index.add(sub_emb)
        faiss.write_index(sub_index, str(sub_dir / "index.faiss"))
        with (sub_dir / "rows.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for r in sub_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = {
        "version": version,
        "embedding_model": model_name,
        "embedding_dim": dim,
        "device": device,
        "rows": len(rows),
        "index_path": str(out_index),
        "rows_path": str(out_rows),
    }
    write_json(sapbert_root / "manifest.json", manifest)

    report = {
        "stage": "07_build_sapbert_index",
        "version": version,
        "inputs": {"entity_catalog": str(entity_catalog)},
        "counts": {"rows": len(rows), "embedding_dim": dim},
        "outputs": {"index": str(out_index), "rows": str(out_rows), "manifest": str(sapbert_root / "manifest.json")},
    }
    write_json(report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw_root", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--model_name", default="models/sapbert")
    ap.add_argument("--batch_size", type=int, default=64)
    ap.add_argument("--max_length", type=int, default=64)
    ap.add_argument("--local_files_only", action="store_true", default=False)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    report = build(
        raw_root=Path(args.raw_root),
        out_dir=Path(args.out_dir),
        version=args.version,
        model_name=args.model_name,
        batch_size=args.batch_size,
        max_length=args.max_length,
        local_files_only=args.local_files_only,
    )
    print(
        f"[07] wrote {report['outputs']['index']} "
        f"({report['counts']['rows']} rows)"
    )


if __name__ == "__main__":
    main()
