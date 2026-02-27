# -*- coding: utf-8 -*-
"""
Hybrid NER:
    - ML NER output (SciSpacy / BC5CDR)
    - Dictionary-based NER for high recall
    - Fully normalized
    - Future-proof for large KG expansions (UMLS)
"""

from typing import List, Tuple, Dict
from .entity_linking_adapter import normalize_surface


class HybridNER:
    def __init__(self, surf2cui_dict: Dict[str, List[str]]):
        self.surf2cui = surf2cui_dict
        self.surfaces = list(surf2cui_dict.keys())

    def dict_detect(self, text: str) -> List[Tuple[str, str]]:
        out = []
        low = text.lower()
        for surf in self.surfaces:
            if surf in low:
                out.append((surf, "DICT"))
        return out

    def merge(
        self, ml_entities: List[Tuple[str, str]], dict_entities: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        out = set()
        for text, label in ml_entities:
            norm = normalize_surface(text)
            if norm:
                out.add((norm, label))
        for surf, label in dict_entities:
            norm = normalize_surface(surf)
            if norm:
                out.add((norm, label))
        return list(out)
