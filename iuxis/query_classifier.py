"""
Query Classifier for Tier-Aware Retrieval

Pattern-based classification of user queries to route to appropriate retrieval strategies.
Zero latency (no LLM calls), production-ready.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class QueryType(Enum):
    """Query types that map to different retrieval strategies."""
    FACTUAL_LOOKUP = "factual_lookup"           # Simple fact retrieval: "How many projects?"
    CURRENT_STATE = "current_state"             # Current status: "What's the current architecture?"
    TEMPORAL_CHAIN = "temporal_chain"           # Evolution over time: "How did X evolve?"
    CROSS_PROJECT_SYNTHESIS = "cross_project_synthesis"  # Multi-project patterns
    RECENT_CONTEXT = "recent_context"           # Recent activity: "What did I work on yesterday?"


@dataclass
class ClassifiedQuery:
    """Result of query classification."""
    query_type: QueryType
    confidence: float  # 0.0-1.0
    entities_mentioned: List[str] = field(default_factory=list)
    time_scope: Optional[str] = None  # "today", "week", "month", "quarter", etc.
    project_hints: List[str] = field(default_factory=list)
    strategy_notes: str = ""  # Human-readable explanation


# Pattern libraries for each query type
FACTUAL_PATTERNS = [
    (r'\bhow many\b', 0.8),
    (r'\bcount\b.*\b(projects|tasks|entries|knowledge)', 0.7),
    (r'\blist (all|my)\b', 0.7),
    (r'\bwho is\b', 0.8),
    (r'\bwhat is (the )?(definition|meaning)', 0.8),
    (r'\b(email|phone|contact|address)\b', 0.7),
]

CURRENT_STATE_PATTERNS = [
    (r'\bcurrent (state|status|architecture|design|approach)\b', 0.9),
    (r'\bwhat (is|are) (the )?(current|latest|now)\b', 0.85),
    (r'\bright now\b', 0.8),
    (r'\btoday\'s (status|state)\b', 0.8),
    (r'\bwhere (are we|am I) (at|now|currently)', 0.85),
    (r'\bwhat\'s the (latest|current)\b', 0.85),
    (r'\bactive (projects|tasks|items)\b', 0.7),
]

TEMPORAL_CHAIN_PATTERNS = [
    (r'\bhow (did|has).*(evolve|change|develop|progress)', 0.9),
    (r'\b(evolution|progression|development|history) of\b', 0.85),
    (r'\bover time\b', 0.8),
    (r'\bfrom.*to\b.*\b(now|today|present)', 0.75),
    (r'\btimeline\b', 0.8),
    (r'\bchronological\b', 0.9),
    (r'\btrend\b', 0.7),
]

CROSS_PROJECT_PATTERNS = [
    (r'\bacross (all |my )?(projects|repos|codebases)\b', 0.9),
    (r'\bcommon (patterns|themes|blockers|issues)\b', 0.85),
    (r'\b(similarities|differences) (between|across)\b', 0.8),
    (r'\ball (of |my )?(projects|repos)\b', 0.75),
    (r'\bevery project\b', 0.8),
    (r'\bglobal\b.*\b(view|overview|summary)\b', 0.75),
]

RECENT_CONTEXT_PATTERNS = [
    (r'\b(yesterday|today|this (week|morning))\b', 0.9),
    (r'\b(recently|lately|last (few )?days)\b', 0.85),
    (r'\bwhat (did I|have I).*(yesterday|today|recently)\b', 0.9),
    (r'\brecent (activity|work|changes|updates)\b', 0.85),
    (r'\bpast (24 hours|week|few days)\b', 0.8),
    (r'\bsince (yesterday|last week|monday)\b', 0.8),
]

# Project fragment detection
PROJECT_FRAGMENTS = {
    'novabrew': ['novabrew', 'nova brew'],
    'orbit-marketing': ['orbit', 'orbit marketing'],
    'iuxis': ['iuxis', 'intelligence platform'],
}

# Time scope extraction patterns
TIME_SCOPE_PATTERNS = [
    (r'\btoday\b', 'today'),
    (r'\byesterday\b', 'yesterday'),
    (r'\bthis week\b', 'week'),
    (r'\blast week\b', 'last_week'),
    (r'\bthis month\b', 'month'),
    (r'\bthis quarter\b', 'quarter'),
    (r'\brecent(ly)?\b', 'recent'),
    (r'\bpast (24 hours|few days)\b', 'recent'),
]


def classify_query(query: str) -> ClassifiedQuery:
    """
    Classify a user query into a QueryType with confidence score.

    Uses pattern matching with weighted scoring. Returns the highest-scoring
    classification with supporting metadata.

    Args:
        query: User's natural language query

    Returns:
        ClassifiedQuery with type, confidence, and extracted metadata
    """
    query_lower = query.lower()

    # Score each query type
    scores = {
        QueryType.FACTUAL_LOOKUP: _score_patterns(query_lower, FACTUAL_PATTERNS),
        QueryType.CURRENT_STATE: _score_patterns(query_lower, CURRENT_STATE_PATTERNS),
        QueryType.TEMPORAL_CHAIN: _score_patterns(query_lower, TEMPORAL_CHAIN_PATTERNS),
        QueryType.CROSS_PROJECT_SYNTHESIS: _score_patterns(query_lower, CROSS_PROJECT_PATTERNS),
        QueryType.RECENT_CONTEXT: _score_patterns(query_lower, RECENT_CONTEXT_PATTERNS),
    }

    # Get highest scoring type
    best_type = max(scores, key=scores.get)
    confidence = scores[best_type]

    # If no clear match, default to CURRENT_STATE (safest fallback)
    if confidence < 0.3:
        best_type = QueryType.CURRENT_STATE
        confidence = 0.5

    # Extract metadata
    entities = _extract_entities(query)
    time_scope = _extract_time_scope(query_lower)
    project_hints = _extract_project_hints(query_lower)

    # Generate strategy notes
    strategy_notes = _generate_strategy_notes(best_type, confidence, time_scope, project_hints)

    return ClassifiedQuery(
        query_type=best_type,
        confidence=confidence,
        entities_mentioned=entities,
        time_scope=time_scope,
        project_hints=project_hints,
        strategy_notes=strategy_notes,
    )


def _score_patterns(text: str, patterns: List[tuple]) -> float:
    """Score text against a list of (pattern, weight) tuples."""
    score = 0.0
    matches = 0

    for pattern, weight in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
            matches += 1

    # Normalize: cap at 1.0, boost if multiple matches
    if matches > 0:
        score = min(1.0, score / max(1, matches * 0.7))

    return score


def _extract_entities(query: str) -> List[str]:
    """Extract mentioned entities (capitalized phrases, technical terms)."""
    entities = []

    # Find capitalized words (likely proper nouns)
    capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
    entities.extend(capitalized)

    # Find technical terms (camelCase, snake_case)
    technical = re.findall(r'\b[a-z]+[A-Z][a-zA-Z]*\b|\b[a-z]+_[a-z_]+\b', query)
    entities.extend(technical)

    return list(set(entities))[:5]  # Max 5 entities


def _extract_time_scope(text: str) -> Optional[str]:
    """Extract time scope from query."""
    for pattern, scope in TIME_SCOPE_PATTERNS:
        if re.search(pattern, text):
            return scope
    return None


def _extract_project_hints(text: str) -> List[str]:
    """Extract project hints from query."""
    hints = []
    for project_name, fragments in PROJECT_FRAGMENTS.items():
        for fragment in fragments:
            if fragment in text:
                hints.append(project_name)
                break
    return list(set(hints))


def _generate_strategy_notes(
    query_type: QueryType,
    confidence: float,
    time_scope: Optional[str],
    project_hints: List[str],
) -> str:
    """Generate human-readable strategy notes for logging."""
    type_name = query_type.value.replace('_', ' ').title()

    notes = [f"Query classified as {type_name} (conf={confidence:.2f})"]

    if time_scope:
        notes.append(f"time_scope={time_scope}")

    if project_hints:
        notes.append(f"projects={','.join(project_hints)}")

    # Add retrieval strategy hint
    strategy_map = {
        QueryType.FACTUAL_LOOKUP: "Using SQL factual retrieval (topk=5)",
        QueryType.CURRENT_STATE: "Entity states primary + recent supplement (topk=5)",
        QueryType.TEMPORAL_CHAIN: "Chronological sort, increased topk=15",
        QueryType.CROSS_PROJECT_SYNTHESIS: "Cross-project search, no filter (topk=10)",
        QueryType.RECENT_CONTEXT: "Recency-filtered retrieval (topk=12)",
    }
    notes.append(strategy_map[query_type])

    return " | ".join(notes)
