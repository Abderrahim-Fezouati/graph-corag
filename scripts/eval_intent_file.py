import json, sys, numpy as np
from pathlib import Path
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch


def load_jsonl(path):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def make_id2label(cfg):
    """
    Return a robust id->label function that tolerates:
      - dict with int keys
      - dict with str keys
      - dict with 'LABEL_0' keys
      - list of labels
    """
    id2label = getattr(cfg, "id2label", None)
    if isinstance(id2label, list):
        return lambda pid: id2label[pid]
    if isinstance(id2label, dict):

        def _get(pid):
            if pid in id2label:
                return id2label[pid]
            s = str(pid)
            if s in id2label:
                return id2label[s]
            k = f"LABEL_{pid}"
            if k in id2label:
                return id2label[k]
            # fallback: try to map via sorted numeric keys if possible
            try:
                keys = sorted(id2label.keys(), key=lambda x: int(str(x).split("_")[-1]))
                return id2label[keys[pid]]
            except Exception:
                raise KeyError(f"Cannot map class id {pid} with id2label={id2label}")

        return _get
    # final fallback: assume 0,1,2 -> 'LABEL_i'
    return lambda pid: f"LABEL_{pid}"


def predict_batch(model_dir, questions, max_length=128, batch_size=32):
    tok = AutoTokenizer.from_pretrained(model_dir)
    mdl = AutoModelForSequenceClassification.from_pretrained(model_dir)
    map_id = make_id2label(mdl.config)
    mdl.eval()
    preds = []
    for i in range(0, len(questions), batch_size):
        chunk = questions[i : i + batch_size]
        x = tok(
            chunk,
            truncation=True,
            max_length=max_length,
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = mdl(**x).logits
        pred_ids = torch.argmax(logits, dim=-1).cpu().tolist()
        preds.extend([map_id(pid) for pid in pred_ids])
    return preds


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--model_dir", required=True)
    ap.add_argument("--file", required=True)
    args = ap.parse_args()

    data = load_jsonl(args.file)
    y_true = [d["label"] for d in data]
    qs = [d["question"] for d in data]
    y_pred = predict_batch(args.model_dir, qs)

    print("Samples:", len(data))
    print("Accuracy:", accuracy_score(y_true, y_pred))
    print("\nPer-class report:\n", classification_report(y_true, y_pred, digits=3))
    print("Confusion matrix (rows=true, cols=pred):")
    labs = sorted(set(y_true + y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labs)
    print("labels:", labs)
    print(cm)


if __name__ == "__main__":
    main()
