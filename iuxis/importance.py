"""
Importance scoring for knowledge entries.
Heuristic-based, no LLM call required. Computed at write time.
Score range: 0.0 to 1.0
"""

import math
from typing import Optional


CATEGORY_SCORES = {
    "decision":      0.30,
    "architecture":  0.28,
    "compliance":    0.25,
    "risk":          0.22,
    "fact":          0.18,
    "metric":        0.18,
    "relationship":  0.12,
    "context":       0.08,
    "task":          0.15,
}

SOURCE_SCORES = {
    "manual":       0.10,
    "ingestion":    0.08,
    "chat":         0.06,
    "system":       0.02,
    "consolidation": 0.00,  # Already high-importance by design
}

CONFIDENCE_SCORES = {
    "high":   0.08,
    "medium": 0.04,
    "low":    0.00,
}


def compute_importance(
    category: str,
    content: str,
    source: str = "ingestion",
    confidence: str = "high",
    pinned: bool = False,
) -> float:
    """
    Compute importance score for a knowledge entry.

    Args:
        category:   Knowledge category (decision, fact, risk, etc.)
        content:    The actual knowledge text
        source:     Where this knowledge came from
        confidence: Confidence level
        pinned:     Whether user has explicitly pinned this entry

    Returns:
        float in [0.0, 1.0]
    """
    base = 0.35

    category_bonus   = CATEGORY_SCORES.get(category, 0.10)
    source_bonus     = SOURCE_SCORES.get(source, 0.05)
    confidence_bonus = CONFIDENCE_SCORES.get(confidence, 0.04)

    # Content signals (cheap string ops, no LLM)
    words = content.split()
    length_bonus  = min(0.10, math.log1p(len(words)) / 35.0)
    number_bonus  = 0.04 if any(c.isdigit() for c in content) else 0.0
    url_bonus     = 0.03 if "http" in content else 0.0
    name_bonus    = 0.03 if any(w[0].isupper() for w in words if len(w) > 3) else 0.0

    pin_bonus = 0.35 if pinned else 0.0

    score = (base + category_bonus + source_bonus + confidence_bonus
             + length_bonus + number_bonus + url_bonus + name_bonus + pin_bonus)
    return float(min(1.0, score))
