# -*- coding: utf-8 -*-
"""
kg_validation.predicate_schema

Defines semantic classes for KG predicates and explicit
antagonistic (contradictory) predicate pairs.

This file is intentionally:
- Static
- Interpretable
- Review-friendly
"""

from __future__ import annotations
from typing import Dict, Set, Tuple


# -------------------------------------------------
# Predicate polarity / semantic class
# -------------------------------------------------

PREDICATE_CLASSES: Dict[str, str] = {
    # Positive / beneficial
    "TREATS": "positive",
    "AMELIORATES": "positive",
    "PREVENTS": "positive",
    "INHIBITS": "positive",
    # Negative / harmful
    "CAUSES": "negative",
    "INDUCES": "negative",
    "ADVERSE_EFFECT": "negative",
    "CONTRAINDICATED_FOR": "negative",
    # Neutral / descriptive
    "INTERACTS_WITH": "neutral",
    "ASSOCIATED_WITH": "neutral",
    "BINDS": "neutral",
    "TARGETS": "neutral",
}


# -------------------------------------------------
# Explicit antagonistic predicate pairs
# (order does not matter)
# -------------------------------------------------

ANTAGONISTIC_PAIRS: Set[Tuple[str, str]] = {
    ("TREATS", "CAUSES"),
    ("TREATS", "ADVERSE_EFFECT"),
    ("TREATS", "CONTRAINDICATED_FOR"),
    ("PREVENTS", "CAUSES"),
    ("INHIBITS", "ACTIVATES"),
    ("AMELIORATES", "INDUCES"),
}


# -------------------------------------------------
# Helper utilities
# -------------------------------------------------


def normalize_predicate(p: str) -> str:
    return (p or "").strip().upper()


def predicate_class(p: str) -> str:
    """
    Returns semantic class of predicate.
    Defaults to 'neutral' if unknown.
    """
    return PREDICATE_CLASSES.get(normalize_predicate(p), "neutral")


def is_antagonistic(p1: str, p2: str) -> bool:
    """
    Checks whether two predicates are antagonistic.
    """
    a = normalize_predicate(p1)
    b = normalize_predicate(p2)
    return (a, b) in ANTAGONISTIC_PAIRS or (b, a) in ANTAGONISTIC_PAIRS
