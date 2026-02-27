# -*- coding: utf-8 -*-
"""
Offline BioBERT Relation Classifier
"""

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from pathlib import Path


class RelationClassifier:

    LABELS = ["INTERACTS_WITH", "ADVERSE_EFFECT", "CAUSES", "NO_RELATION"]

    def __init__(self, model_root="models/biobert-base-cased-v1.2"):
        print("[RelationClassifier] Loading BioBERT offline from:")
        print(f"  {model_root}")

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_root, local_files_only=True
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_root, num_labels=len(self.LABELS), local_files_only=True
        )
        self.model.eval()

    def predict(self, text: str) -> str:
        enc = self.tokenizer(text, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = self.model(**enc).logits

        label_id = logits.argmax(dim=-1).item()
        return self.LABELS[label_id]
