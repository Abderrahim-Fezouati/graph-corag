# -*- coding: utf-8 -*-
"""
Passage-level Entity Linking using SapBERTLinkerV2.
"""

from typing import List, Dict
from analyzer.sapbert_linker_v2 import SapBERTLinkerV2
from analyzer.entity_linking_adapter import normalize_surface

class PassageEntityLinker:
    def __init__(self, sapbert: SapBERTLinkerV2):
        self.sapbert = sapbert

    def link(self, entities: List[Dict], topk: int = 3) -> List[Dict]:
        """
        Input:
            [{"text": str, "label": str}]
        Output:
            [{"surface", "kg_id", "score", "entity_type"}]
        """
        linked = []
        for e in entities:
            surface = normalize_surface(e["text"])
            if not surface:
                continue

            cands = self.sapbert.link(surface, topk=topk)
            for c in cands:
                linked.append({
                    "surface": surface,
                    "kg_id": c.get("kg_id"),
                    "score": c.get("score", 0.0),
                    "entity_type": c.get("entity_type")
                })
        return linked
