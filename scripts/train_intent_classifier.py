import argparse, json, os, sys
from pathlib import Path
from typing import Dict

import numpy as np
from datasets import load_dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    DataCollatorWithPadding,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
)
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
)


def read_label_map(dir_path: str) -> Dict[str, int]:
    lm = Path(dir_path, "label_map.json")
    if lm.exists():
        with open(lm, "r", encoding="utf-8") as f:
            j = json.load(f)
        # support either {"label2id": {...}} or a flat dict
        if isinstance(j, dict) and "label2id" in j:
            return {str(k): int(v) for k, v in j["label2id"].items()}
        return {str(k): int(v) for k, v in j.items()}
    # fallback
    return {"factoid": 0, "yesno": 1, "list": 2}


def compute_metrics_fn(id2label):
    def _cm(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = accuracy_score(labels, preds)
        p, r, f1, _ = precision_recall_fscore_support(
            labels, preds, average="macro", zero_division=0
        )
        return {
            "accuracy": acc,
            "macro_f1": f1,
            "macro_precision": p,
            "macro_recall": r,
        }

    return _cm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data_dir",
        required=True,
        help="Folder containing train.jsonl / val.jsonl / test.jsonl and label_map.json",
    )
    ap.add_argument("--train_file", default="train.jsonl")
    ap.add_argument("--val_file", default="val.jsonl")
    ap.add_argument("--test_file", default="test.jsonl")
    ap.add_argument(
        "--model_name",
        default="distilbert-base-uncased",
        help="e.g. distilbert-base-uncased or allenai/biomed_roberta_base",
    )
    ap.add_argument(
        "--out_dir", required=True, help="Output directory for model/checkpoints"
    )
    ap.add_argument("--max_length", type=int, default=128)
    ap.add_argument("--batch_size", type=int, default=8)
    ap.add_argument("--grad_accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=float, default=4.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    label2id = read_label_map(str(data_dir))
    id2label = {v: k for k, v in label2id.items()}

    # load datasets
    files = {
        "train": str(data_dir / args.train_file),
        "validation": str(data_dir / args.val_file),
        "test": str(data_dir / args.test_file),
    }
    ds: DatasetDict = load_dataset("json", data_files=files)

    # ensure label is mapped to ids
    def lab2id(ex):
        lbl = str(ex["label"]).lower().strip()
        ex["labels"] = label2id[lbl]
        return ex

    ds = ds.map(lab2id)

    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_fast=True)

    def tok(ex):
        return tokenizer(ex["question"], truncation=True, max_length=args.max_length)

    ds_tok = ds.map(
        tok,
        batched=True,
        remove_columns=[
            c for c in ds["train"].column_names if c not in ("label", "labels", "id")
        ],
    )
    collator = DataCollatorWithPadding(tokenizer=tokenizer)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name, num_labels=len(label2id), id2label=id2label, label2id=label2id
    )

    training_args = TrainingArguments(
        output_dir=args.out_dir,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=max(8, args.batch_size),
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        weight_decay=0.01,
        warmup_ratio=0.06,
        logging_steps=50,
        fp16=True,
        report_to="none",
        seed=args.seed,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ds_tok["train"],
        eval_dataset=ds_tok["validation"],
        tokenizer=tokenizer,
        data_collator=collator,
        compute_metrics=compute_metrics_fn(id2label),
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    trainer.train()

    # evaluate on validation + test
    val_metrics = trainer.evaluate(ds_tok["validation"])
    print("Validation metrics:", val_metrics)

    test_metrics = trainer.evaluate(ds_tok["test"])
    print("Test metrics:", test_metrics)

    # detailed per-class report on test
    preds = np.argmax(trainer.predict(ds_tok["test"]).predictions, axis=-1)
    y_true = np.array([ex["labels"] for ex in ds_tok["test"]])
    print("Test classification report:")
    print(
        classification_report(
            y_true, preds, target_names=[id2label[i] for i in sorted(id2label)]
        )
    )

    # final save
    trainer.save_model(args.out_dir)
    tokenizer.save_pretrained(args.out_dir)
    # also save the label maps explicitly
    with open(Path(args.out_dir, "label_map.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"label2id": label2id, "id2label": id2label},
            f,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
