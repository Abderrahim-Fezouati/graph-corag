import argparse, json
from pathlib import Path
import numpy as np

from datasets import load_dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    DataCollatorWithPadding,
    Trainer,
    EarlyStoppingCallback,
)
from transformers.training_args import TrainingArguments
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
)


def read_label_map(dir_path):
    lm = Path(dir_path, "label_map.json")
    if lm.exists():
        j = json.loads(lm.read_text(encoding="utf-8"))
        if isinstance(j, dict) and "label2id" in j:
            return {str(k): int(v) for k, v in j["label2id"].items()}
        return {str(k): int(v) for k, v in j.items()}
    return {"factoid": 0, "yesno": 1, "list": 2}


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    acc = accuracy_score(labels, preds)
    p, r, f1, _ = precision_recall_fscore_support(
        labels, preds, average="macro", zero_division=0
    )
    return {"accuracy": acc, "macro_f1": f1, "macro_precision": p, "macro_recall": r}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--train_file", default="train.jsonl")
    ap.add_argument("--val_file", default="val.jsonl")
    ap.add_argument("--test_file", default="test.jsonl")
    ap.add_argument("--model_name", default="distilbert-base-uncased")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--max_length", type=int, default=128)
    ap.add_argument("--batch_size", type=int, default=8)
    ap.add_argument("--grad_accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=float, default=4.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    label2id = read_label_map(args.data_dir)
    id2label = {v: k for k, v in label2id.items()}

    files = {
        "train": str(Path(args.data_dir, args.train_file)),
        "validation": str(Path(args.data_dir, args.val_file)),
        "test": str(Path(args.data_dir, args.test_file)),
    }
    ds: DatasetDict = load_dataset("json", data_files=files)

    # map string label -> int labels
    def lab2id(ex):
        ex["labels"] = label2id[str(ex["label"]).lower().strip()]
        return ex

    ds = ds.map(lab2id)

    tok = AutoTokenizer.from_pretrained(args.model_name, use_fast=True)

    # tokenize; DROP raw 'label' and 'question' so batches only have tensors
    def tokenize(ex):
        return tok(ex["question"], truncation=True, max_length=args.max_length)

    cols_to_keep = {"labels", "id"}  # keep numeric labels and (optionally) id
    cols_to_remove = [c for c in ds["train"].column_names if c not in cols_to_keep]
    ds_tok = ds.map(tokenize, batched=True, remove_columns=cols_to_remove)

    collator = DataCollatorWithPadding(tokenizer=tok)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name, num_labels=len(label2id), id2label=id2label, label2id=label2id
    )

    # Use eval_strategy for your installed transformers
    training_args = TrainingArguments(
        output_dir=args.out_dir,
        eval_strategy="epoch",
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
        logging_strategy="steps",
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
        tokenizer=tok,  # deprecation warning is fine on 4.57.1
        data_collator=collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    trainer.train()
    print("Validation metrics:", trainer.evaluate(ds_tok["validation"]))

    out = trainer.predict(ds_tok["test"])
    preds = np.argmax(out.predictions, axis=-1)
    y_true = out.label_ids
    print("Test classification report:")
    print(
        classification_report(
            y_true, preds, target_names=[id2label[i] for i in sorted(id2label)]
        )
    )

    trainer.save_model(args.out_dir)
    tok.save_pretrained(args.out_dir)
    Path(args.out_dir, "label_map.json").write_text(
        json.dumps({"label2id": label2id, "id2label": id2label}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
