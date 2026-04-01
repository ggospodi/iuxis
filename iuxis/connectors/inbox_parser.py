"""
Inbox filename parser — Smart routing with fuzzy matching + LLM classification.

Routing priority:
  1. Filename fuzzy match (80+ score threshold)
  2. LLM content classification (0.75+ confidence)
  3. Unassigned queue
"""

import re
import os
from pathlib import Path
from difflib import SequenceMatcher
from typing import Optional
import logging

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75
FUZZY_THRESHOLD = 80  # 0–100 scale


def parse_filename_project_token(filename: str) -> Optional[str]:
    """
    Extract project token from filename.
    Handles formats:
      - title_projectname_YYYYMMDD.md   → "projectname"
      - title_projectname_YYYYDDMM.md   → "projectname"
      - projectname_title_YYYYMMDD.md   → "projectname" (first token tried)
      - projectname_YYYYMMDD.md         → "projectname"
    Strategy: split on underscores, filter out date-shaped tokens,
    return the token(s) most likely to be a project name.
    """
    stem = Path(filename).stem.lower()
    parts = stem.split('_')

    # Filter out date-shaped tokens (8 digits, or year-like 4 digits)
    non_date_parts = [p for p in parts if not re.match(r'^\d{6,8}$', p) and not re.match(r'^\d{4}$', p)]

    if not non_date_parts:
        return None

    # Return all non-date parts as a joined string for fuzzy matching
    # e.g. ["quarterly", "novabrew", "review"] → "quarterly novabrew review"
    return ' '.join(non_date_parts)


def fuzzy_match_project(token: str, projects: list[dict]) -> tuple[Optional[dict], int]:
    """
    Fuzzy match a token string against all project names.
    Returns (best_project, score) where score is 0-100.
    Checks:
      - Direct substring match (score 95)
      - Token appears in project name (score 90)
      - SequenceMatcher ratio on each word in token vs project name
    """
    best_project = None
    best_score = 0

    token_lower = token.lower()
    token_words = set(token_lower.split())

    for project in projects:
        name = project['name'].lower()
        name_words = set(name.split())
        name_slug = name.replace(' ', '-')

        # Direct substring: "novabrew" in "novabrew" → 95
        for word in token_words:
            if word in name and len(word) >= 4:
                score = 95
                if score > best_score:
                    best_score = score
                    best_project = project
                    break

        # Name-as-slug match
        if name_slug and name_slug in token_lower:
            score = 90
            if score > best_score:
                best_score = score
                best_project = project

        # SequenceMatcher fallback
        ratio = int(SequenceMatcher(None, token_lower, name).ratio() * 100)
        if ratio > best_score:
            best_score = ratio
            best_project = project

    return best_project, best_score


def classify_by_content(content: str, projects: list[dict]) -> dict:
    """
    Use LLM to classify file content into a project.
    Returns {"project_id": int, "project_name": str, "confidence": float, "reasoning": str}
    Falls back to unassigned if LLM call fails.
    """
    # Use singleton pattern to avoid module-level instantiation
    def _get_llm():
        from iuxis.llm_client import LLMClient
        return LLMClient()

    project_list = '\n'.join([
        f"- {p['name']}: {p.get('description', 'No description')}"
        for p in projects
    ])

    prompt = f"""You are classifying a document into one of these projects:

{project_list}

Document content (first 2000 chars):
{content[:2000]}

Respond with JSON only:
{{"project_name": "<exact project name from list above or null if unclear>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}

If the document clearly belongs to a project, confidence should be 0.75+.
If ambiguous or no match, set project_name to null and confidence below 0.5."""

    try:
        llm = _get_llm()
        response = llm.generate(
            prompt=prompt,
            system_prompt="You classify documents into projects. Respond with valid JSON only, no other text."
        )

        # Strip CJK characters
        response = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]+', '', response)

        import json
        # Strip any thinking blocks or markdown
        clean = re.sub(r'```json|```', '', response).strip()
        # Find JSON object
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if match:
            result = json.loads(match.group())
            # Map name back to project id
            project_name = result.get('project_name')
            if project_name:
                for p in projects:
                    if p['name'].lower() == project_name.lower():
                        return {
                            'project_id': p['id'],
                            'project_name': p['name'],
                            'confidence': float(result.get('confidence', 0)),
                            'reasoning': result.get('reasoning', '')
                        }
    except Exception as e:
        logger.warning(f"[InboxParser] LLM classification failed: {e}")

    return {'project_id': None, 'project_name': None, 'confidence': 0.0, 'reasoning': 'Classification failed'}


def route_file(filepath: str, projects: list[dict]) -> dict:
    """
    Main routing function. Returns:
    {
        "project_id": int or None,
        "project_name": str or None,
        "route_method": "filename_fuzzy" | "llm_content" | "unassigned",
        "confidence": float,
        "reasoning": str
    }
    """
    filename = os.path.basename(filepath)

    # Step 1: Filename fuzzy match
    token = parse_filename_project_token(filename)
    if token:
        project, score = fuzzy_match_project(token, projects)
        if project and score >= FUZZY_THRESHOLD:
            logger.info(f"[InboxParser] Filename match: '{filename}' → '{project['name']}' (score={score})")
            return {
                'project_id': project['id'],
                'project_name': project['name'],
                'route_method': 'filename_fuzzy',
                'confidence': score / 100,
                'reasoning': f"Filename token '{token}' matched project name (score={score})"
            }

    # Step 2: LLM content classification
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"[InboxParser] Could not read file {filepath}: {e}")
        return {'project_id': None, 'project_name': None, 'route_method': 'unassigned', 'confidence': 0.0, 'reasoning': 'Could not read file'}

    result = classify_by_content(content, projects)

    if result['confidence'] >= CONFIDENCE_THRESHOLD and result['project_id']:
        logger.info(f"[InboxParser] LLM match: '{filename}' → '{result['project_name']}' (confidence={result['confidence']:.2f})")
        result['route_method'] = 'llm_content'
        return result

    # Step 3: Unassigned
    logger.info(f"[InboxParser] Unassigned: '{filename}' (confidence={result['confidence']:.2f})")
    return {
        'project_id': None,
        'project_name': None,
        'route_method': 'unassigned',
        'confidence': result['confidence'],
        'reasoning': result.get('reasoning', 'Below confidence threshold')
    }
