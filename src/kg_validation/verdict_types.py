# -*- coding: utf-8 -*-
"""
kg_validation.verdict_types

Centralized verdict and reason taxonomy.
Scientifically conservative and reviewer-safe.
"""

from enum import Enum


class Verdict(str, Enum):
    SUPPORTED = "supported"
    WEAKLY_SUPPORTED = "weakly_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    INVALID_ENTITY = "invalid_entity"
    SEMANTIC_MISMATCH = "semantic_mismatch"


class VerdictReason(str, Enum):
    EXACT_MATCH = "exact_match"
    RELAXED_PREDICATE_MATCH = "relaxed_predicate_match"
    ANTAGONISTIC_PREDICATE = "antagonistic_predicate"
    NO_EDGE = "no_edge"
    GROUNDING_FAILURE = "grounding_failure"
