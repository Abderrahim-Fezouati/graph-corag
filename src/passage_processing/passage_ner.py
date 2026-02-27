# -*- coding: utf-8 -*-
"""
Passage-level NER wrapper.
Reuses the same NER model used for queries.
"""

from typing import List, Dict


class PassageNER:
    def __init__(self, ner_model):
        """
        ner_model: your existing NER object (already loaded elsewhere)
        """
        self.ner = ner_model

    def extract_entities(self, text: str) -> List[Dict]:
        """
        Returns list of entities:
        [{"text": str, "label": str}]
        """
        if not text:
            return []

        ents = self.ner(text)
        out = []
        for e in ents:
            if "text" in e and e["text"].strip():
                out.append({"text": e["text"], "label": e.get("label", "UNK")})
        return out
