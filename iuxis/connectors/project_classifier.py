"""
Project classifier — LLM-based content classification for unassigned files.

Thin wrapper exposing classify_by_content() for use outside the connector context
(e.g. re-classification from the UI).
"""

from iuxis.connectors.inbox_parser import classify_by_content, fuzzy_match_project, parse_filename_project_token
from iuxis.db import fetch_all


def get_all_projects_for_classification() -> list[dict]:
    """Fetch all active projects with name + description for classifier context."""
    rows = fetch_all("SELECT id, name, description FROM projects WHERE status = 'active' ORDER BY priority")
    return rows


def reclassify_entry(entry_id: int) -> dict:
    """Re-run classification on a specific knowledge entry. Used by the unassigned queue UI."""
    from iuxis.db import fetch_one
    entry = fetch_one("SELECT * FROM user_knowledge WHERE id = ?", (entry_id,))
    if not entry:
        return {'error': 'Entry not found'}
    projects = get_all_projects_for_classification()
    return classify_by_content(entry['content'], projects)
