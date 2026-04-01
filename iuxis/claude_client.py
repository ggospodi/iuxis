"""Claude API client — prompt assembly, context management, and API calls."""
from __future__ import annotations

import os
from pathlib import Path
from datetime import date, datetime
from typing import Optional

import anthropic

from iuxis.db import load_config, fetch_all
from iuxis.project_manager import get_all_projects_summary
from iuxis.task_manager import get_all_tasks_summary, get_todays_tasks, get_upcoming_tasks
from iuxis.models import Task


# ---------------------------------------------------------------------------
# Config & Client
# ---------------------------------------------------------------------------

_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        cfg = load_config()
        api_key = os.environ.get(cfg["claude"]["api_key_env"])
        if not api_key:
            raise RuntimeError(
                f"API key not found. Set {cfg['claude']['api_key_env']} environment variable."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def get_model(deep: bool = False) -> str:
    cfg = load_config()
    if deep:
        return cfg["claude"]["deep_analysis_model"]
    return cfg["claude"]["default_model"]


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Chief of Staff for a technology executive managing 12-15 concurrent \
projects. Your job is to optimize his time, surface insights, and coach him toward maximum \
productivity. 

Your principles:
- Be direct, specific, and actionable. Never be vague.
- When suggesting priorities, give concrete reasons tied to deadlines, dependencies, or impact.
- When coaching, reference specific patterns from activity data.
- When creating tasks or updating projects, output structured commands (see below).
- Keep responses concise — the user is busy.

When the user asks you to create or modify data, respond with both:
1. A human-readable confirmation of what you're doing
2. A JSON action block that the system will parse and execute

Action format:
```json
{{"action": "create_task", "params": {{"title": "...", "project": "...", "priority": 3, "due_date": "YYYY-MM-DD", "estimated_hours": 2.0}}}}
```
```json
{{"action": "update_task", "params": {{"task_id": 1, "status": "done"}}}}
```
```json
{{"action": "create_project", "params": {{"name": "...", "type": "product", "priority": 3, "description": "..."}}}}
```
```json
{{"action": "update_project", "params": {{"project_id": 1, "priority": 2, "current_focus": "..."}}}}
```

Multiple actions can be included in a single response. The system will execute them and confirm.

Today's date: {today}
Current time: {now}
"""


# ---------------------------------------------------------------------------
# Context Assembly
# ---------------------------------------------------------------------------

def assemble_context(
    user_message: str,
    include_obsidian: Optional[str] = None,
    chat_history: Optional[list[dict]] = None,
) -> tuple[str, list[dict]]:
    """Assemble system prompt + context + conversation messages.
    
    Returns (system_prompt, messages_list).
    """
    cfg = load_config()
    now = datetime.now()

    # Build system prompt
    system = SYSTEM_PROMPT.format(
        today=date.today().isoformat(),
        now=now.strftime("%H:%M"),
    )

    # Build context block
    context_parts = []

    # Projects summary
    context_parts.append(get_all_projects_summary())

    # Today's tasks
    todays = get_todays_tasks()
    if todays:
        lines = ["TODAY'S TASKS:"]
        for t in todays:
            proj = f" [{t.project_name}]" if t.project_name else ""
            lines.append(f"  #{t.id}{proj}: {t.summary()}")
        context_parts.append("\n".join(lines))

    # Active tasks summary
    context_parts.append(get_all_tasks_summary())

    # Upcoming deadlines
    upcoming = get_upcoming_tasks(7)
    if upcoming:
        lines = ["UPCOMING (7 DAYS):"]
        for t in upcoming:
            lines.append(f"  #{t.id} [{t.project_name}]: {t.title} — due {t.due_date}")
        context_parts.append("\n".join(lines))

    # Recent activity (last 48h)
    activity = fetch_all(
        """SELECT * FROM activity_log
           WHERE created_at > datetime('now', '-2 days')
           ORDER BY created_at DESC LIMIT 20"""
    )
    if activity:
        lines = ["RECENT ACTIVITY (48h):"]
        for a in activity:
            lines.append(f"  [{a['event_type']}] {a.get('details', '')} @ {a['created_at']}")
        context_parts.append("\n".join(lines))

    # Recent insights
    insights = fetch_all(
        "SELECT * FROM insights WHERE status = 'new' ORDER BY created_at DESC LIMIT 5"
    )
    if insights:
        lines = ["UNRESOLVED INSIGHTS:"]
        for i in insights:
            lines.append(f"  [{i['severity']}] {i['content']}")
        context_parts.append("\n".join(lines))

    # Obsidian context (if provided)
    if include_obsidian:
        context_parts.append(f"VAULT SEARCH RESULTS:\n{include_obsidian}")

    # Combine context
    context_block = "\n\n---\n\n".join(context_parts)

    # Build messages
    messages = []

    # Add chat history (last 10 exchanges)
    if chat_history:
        for msg in chat_history[-20:]:  # last 10 pairs
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message with context
    full_user_message = f"""CURRENT CONTEXT:
{context_block}

---

USER MESSAGE:
{user_message}"""

    messages.append({"role": "user", "content": full_user_message})

    return system, messages


# ---------------------------------------------------------------------------
# API Calls
# ---------------------------------------------------------------------------

def chat(
    user_message: str,
    include_obsidian: Optional[str] = None,
    chat_history: Optional[list[dict]] = None,
    deep: bool = False,
) -> tuple[str, int]:
    """Send a message to Claude and return (response_text, tokens_used).
    
    Args:
        user_message: The user's input
        include_obsidian: Optional vault search results to include as context
        chat_history: Previous chat messages
        deep: Use the deep analysis model (Opus) instead of default (Sonnet)
    
    Returns:
        Tuple of (assistant response text, total tokens used)
    """
    client = get_client()
    model = get_model(deep=deep)
    system, messages = assemble_context(user_message, include_obsidian, chat_history)

    cfg = load_config()
    max_tokens = cfg["claude"].get("max_context_tokens", 8000)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )

    text = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens

    return text, tokens


def generate_briefing() -> tuple[str, int]:
    """Generate the morning briefing."""
    prompt_path = Path(__file__).parent / "prompts" / "daily_briefing.txt"
    prompt_template = prompt_path.read_text()

    cfg = load_config()
    prompt = prompt_template.format(
        work_start=cfg["user"]["work_start"],
        work_end=cfg["user"]["work_end"],
    )

    return chat(prompt)


def analyze_patterns() -> tuple[str, int]:
    """Run pattern analysis on activity data."""
    prompt_path = Path(__file__).parent / "prompts" / "analyze_patterns.txt"
    prompt = prompt_path.read_text()
    return chat(prompt, deep=True)


def prioritize_tasks() -> tuple[str, int]:
    """Get AI-ranked task priorities."""
    prompt_path = Path(__file__).parent / "prompts" / "prioritize_tasks.txt"
    prompt = prompt_path.read_text()
    return chat(prompt)


def query_vault(user_question: str, vault_results: str) -> tuple[str, int]:
    """Ask Claude about vault search results."""
    prompt_path = Path(__file__).parent / "prompts" / "obsidian_query.txt"
    base_prompt = prompt_path.read_text()
    full_prompt = f"{base_prompt}\n\nUser's question: {user_question}"
    return chat(full_prompt, include_obsidian=vault_results)


def call_with_context(
    system_prompt: str,
    context: str,
    user_message: str,
    max_tokens: int = 4096,
) -> tuple[str, int]:
    """Call Claude API with system prompt and context prepended to user message.

    Args:
        system_prompt: System prompt defining Claude's role and behavior
        context: Context block to prepend to user message
        user_message: The user's actual message
        max_tokens: Maximum tokens in response

    Returns:
        Tuple of (assistant response text, total tokens used)
    """
    client = get_client()
    cfg = load_config()
    model = cfg["claude"].get("default_model", "claude-sonnet-3-5-20241022")

    # Prepend context to user message
    full_message = f"{context}\n\n---\n\nUSER MESSAGE:\n{user_message}"

    messages = [{"role": "user", "content": full_message}]

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    )

    text = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens

    return text, tokens
