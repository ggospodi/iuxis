"""Dashboard UI components for Iuxis.

Provides render functions for the 5 main dashboard sections:
1. Today's Focus - priority tasks
2. Project Cards - hierarchical project view with parent-child relationships
3. Recent Knowledge - most recent knowledge entries with project filtering and stats
4. Today's Schedule - schedule blocks from the schedule_blocks table
5. Insights Feed - recent AI-generated insights
"""
from __future__ import annotations

import streamlit as st
from datetime import date, datetime
from typing import Optional

from iuxis.db import fetch_all
from iuxis.project_manager import list_projects, get_project_tree
from iuxis.task_manager import get_todays_tasks, list_tasks
from iuxis.insight_engine import get_recent_insights
from iuxis.models import Project, Task, Insight, ScheduleBlock


# ---------------------------------------------------------------------------
# Section 0: Morning Briefing
# ---------------------------------------------------------------------------

def render_morning_briefing():
    """Display today's morning briefing if available."""
    row = fetch_all(
        """SELECT content, created_at FROM insights
        WHERE type = 'recommendation'
        AND content LIKE '%Morning Briefing%'
        AND date(created_at) = date('now')
        ORDER BY created_at DESC LIMIT 1"""
    )

    if row:
        st.subheader("🌅 Morning Briefing")
        st.markdown(row[0].get("content", ""))
        st.caption(f"Generated at {row[0].get('created_at', 'unknown')}")
    else:
        st.info("No briefing yet today. Type **'generate briefing'** in chat to create one.")


# ---------------------------------------------------------------------------
# Section 1: Today's Focus (Priority Tasks)
# ---------------------------------------------------------------------------

def render_todays_focus():
    """Render today's high-priority tasks."""
    st.subheader("🎯 Today's Focus")

    # Get today's tasks (due today or in progress)
    tasks = get_todays_tasks()

    # Filter to show only high priority (P1, P2) first
    high_priority = [t for t in tasks if t.priority <= 2]
    other_tasks = [t for t in tasks if t.priority > 2]

    if not tasks:
        st.info("No tasks scheduled for today. Great time to tackle something from the backlog!")
        return

    # Render high priority tasks
    if high_priority:
        for task in high_priority:
            _render_task_card(task, highlight=True)

    # Show other tasks in a collapsed section if any
    if other_tasks:
        with st.expander(f"Other tasks today ({len(other_tasks)})", expanded=False):
            for task in other_tasks:
                _render_task_card(task, highlight=False)


def _render_task_card(task: Task, highlight: bool = False):
    """Render a single task card."""
    # Status icon
    status_icons = {
        "todo": "⬜",
        "in_progress": "🔵",
        "blocked": "🔴",
        "done": "✅",
        "cancelled": "❌"
    }
    icon = status_icons.get(task.status.value, "⬜")

    # Priority badge
    priority_colors = {1: "🔴", 2: "🟡", 3: "🟢", 4: "🔵", 5: "⚪"}
    priority_badge = priority_colors.get(task.priority, "⚪")

    # Build the task display
    col1, col2 = st.columns([4, 1])

    with col1:
        task_text = f"{icon} **{task.title}**"
        if highlight:
            st.markdown(f"**{priority_badge} P{task.priority}** | {task_text}")
        else:
            st.markdown(f"{priority_badge} P{task.priority} | {task_text}")

        # Show project and details on a caption line
        details = []
        if task.project_name:
            details.append(f"[{task.project_name}]")
        if task.due_date:
            details.append(f"due {task.due_date}")
        if task.estimated_hours:
            details.append(f"~{task.estimated_hours}h")

        if details:
            st.caption(" · ".join(details))

    with col2:
        # Quick actions could go here in future
        pass


# ---------------------------------------------------------------------------
# Section 2: Project Cards (Hierarchical)
# ---------------------------------------------------------------------------

def render_project_cards():
    """Render project cards with parent-child hierarchy."""
    st.subheader("📋 Projects")

    # Get the project tree (top-level projects with nested children)
    tree = get_project_tree()

    if not tree:
        st.info("No projects yet. Add some via chat or run: `python -m iuxis.seed_data`")
        return

    # Render each top-level project
    for node in tree:
        _render_project_node(node)


def _render_project_node(node: dict, level: int = 0):
    """Recursively render a project node and its children."""
    project: Project = node["project"]
    children: list[dict] = node["children"]

    # Status icon
    status_icons = {
        "active": "🟢",
        "paused": "⏸️",
        "blocked": "🔴",
        "monitoring": "👁️"
    }
    status_icon = status_icons.get(project.status.value, "⚪")

    # Priority color for visual hierarchy
    priority_colors = {1: "🔴", 2: "🟡", 3: "🟢", 4: "🔵", 5: "⚪"}
    priority_badge = priority_colors.get(project.priority, "⚪")

    # Create the project card
    if level == 0:
        # Top-level project: use expander
        has_children = len(children) > 0
        expanded = project.status.value == "active" and has_children

        with st.expander(
            f"{status_icon} **{project.name}** {priority_badge}P{project.priority} — {project.type.value} · {project.time_allocation_hrs_week}h/wk",
            expanded=expanded
        ):
            _render_project_details(project)

            # Render children
            if children:
                st.markdown("**Sub-projects:**")
                for child_node in children:
                    _render_project_node(child_node, level=1)
    else:
        # Sub-project: render as a compact card
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"{status_icon} **{project.name}** {priority_badge}P{project.priority}")
                if project.current_focus:
                    st.caption(project.current_focus)
            with col2:
                st.caption(f"{project.type.value}")
                st.caption(f"{project.time_allocation_hrs_week}h/wk")

            # Show nested children if any (support deeper nesting)
            if children:
                st.caption(f"↳ {len(children)} sub-project(s)")
                for child_node in children:
                    _render_project_node(child_node, level=level+1)


def _render_project_details(project: Project):
    """Render detailed project information inside an expander."""
    if project.current_focus:
        st.markdown(f"**Current Focus:** {project.current_focus}")

    if project.description:
        st.caption(project.description)

    # Show quick stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Priority", f"P{project.priority}")
    with col2:
        st.metric("Status", project.status.value.title())
    with col3:
        st.metric("Time/Week", f"{project.time_allocation_hrs_week}h")

    # Show project tags if any
    if project.tags:
        st.caption(f"Tags: {', '.join(project.tags)}")


# ---------------------------------------------------------------------------
# Section 3: Recent Knowledge
# ---------------------------------------------------------------------------

def render_recent_knowledge():
    """Render recent knowledge entries across all projects."""
    st.subheader("📚 Recent Knowledge")

    # Get all projects for the filter dropdown
    projects = list_projects()
    project_options = ["All Projects"] + [p.name for p in projects]

    # Project filter
    selected_project = st.selectbox(
        "Filter by project",
        options=project_options,
        key="knowledge_project_filter"
    )

    # Build query based on filter
    if selected_project == "All Projects":
        query = """
            SELECT uk.*, p.name as project_name, p.id as project_id
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            ORDER BY uk.created_at DESC
            LIMIT 10
        """
        params = ()
    else:
        query = """
            SELECT uk.*, p.name as project_name, p.id as project_id
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            WHERE p.name = ?
            ORDER BY uk.created_at DESC
            LIMIT 10
        """
        params = (selected_project,)

    rows = fetch_all(query, params)

    if not rows:
        st.info("No knowledge entries found. Start ingesting knowledge via chat!")
        return

    # Get summary stats (total entries and project count)
    if selected_project == "All Projects":
        stats_query = """
            SELECT COUNT(*) as total_entries, COUNT(DISTINCT project_id) as project_count
            FROM user_knowledge
        """
        stats_params = ()
    else:
        stats_query = """
            SELECT COUNT(*) as total_entries, COUNT(DISTINCT uk.project_id) as project_count
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            WHERE p.name = ?
        """
        stats_params = (selected_project,)

    stats = fetch_all(stats_query, stats_params)
    if stats:
        total_entries = stats[0].get("total_entries", 0)
        project_count = stats[0].get("project_count", 0)
        st.caption(f"{total_entries} total entries across {project_count} project(s)")

    # Group entries by date
    from collections import defaultdict
    entries_by_date = defaultdict(list)

    for row in rows:
        # Extract date from created_at
        created_at = row.get("created_at", "")
        entry_date = created_at.split()[0] if created_at else "Unknown"
        entries_by_date[entry_date].append(row)

    # Render entries grouped by date (newest first)
    sorted_dates = sorted(entries_by_date.keys(), reverse=True)

    for entry_date in sorted_dates:
        st.markdown(f"**{entry_date}**")
        for entry in entries_by_date[entry_date]:
            _render_knowledge_entry(entry)
        st.write("")  # Add spacing between date groups

    # Knowledge Stats expander
    _render_knowledge_stats()


def _render_knowledge_entry(entry: dict):
    """Render a single knowledge entry."""
    category = entry.get("category", "general").upper()
    content = entry.get("content", "")
    project_name = entry.get("project_name", "No Project")
    source = entry.get("source", "unknown")

    # Truncate content if too long
    if len(content) > 150:
        content = content[:150] + "..."

    # Format: [CATEGORY] content — Project Name — source file
    st.markdown(f"**[{category}]** {content} — _{project_name}_ — `{source}`")


def _render_knowledge_stats():
    """Render knowledge statistics per project in an expander."""
    with st.expander("📊 Knowledge Stats"):
        # Query entry counts per project
        query = """
            SELECT p.name as project_name, COUNT(uk.id) as entry_count
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            GROUP BY uk.project_id, p.name
            ORDER BY entry_count DESC
        """
        rows = fetch_all(query)

        if not rows:
            st.caption("No knowledge entries yet.")
            return

        # Display as a simple table or list
        for row in rows:
            project_name = row.get("project_name", "No Project")
            entry_count = row.get("entry_count", 0)
            st.markdown(f"**{project_name}**: {entry_count} entries")


# ---------------------------------------------------------------------------
# Section 4: Today's Schedule
# ---------------------------------------------------------------------------

def render_todays_schedule():
    """Render today's schedule blocks."""
    st.subheader("📅 Today's Schedule")

    # Query today's schedule blocks
    today = date.today().isoformat()
    rows = fetch_all(
        """SELECT sb.*, p.name as project_name, t.title as task_title
           FROM schedule_blocks sb
           LEFT JOIN projects p ON sb.project_id = p.id
           LEFT JOIN tasks t ON sb.task_id = t.id
           WHERE sb.date = ?
           ORDER BY sb.start_time ASC""",
        (today,)
    )

    if not rows:
        st.info("No schedule blocks for today. Your time is unstructured—use it wisely!")
        return

    blocks = [ScheduleBlock.from_row(r) for r in rows]

    # Render each block
    for block in blocks:
        _render_schedule_block(block)


def _render_schedule_block(block: ScheduleBlock):
    """Render a single schedule block."""
    # Block type icons
    block_icons = {
        "deep_work": "🧠",
        "admin": "📝",
        "meeting": "👥",
        "break": "☕",
        "review": "📊"
    }
    icon = block_icons.get(block.block_type.value, "📌")

    # Status styling
    status_badges = {
        "planned": "⏳",
        "active": "▶️",
        "completed": "✅",
        "skipped": "⏭️"
    }
    status_badge = status_badges.get(block.status, "⏳")

    # Time range
    start = block.start_time.strftime("%H:%M") if block.start_time else "??"
    end = block.end_time.strftime("%H:%M") if block.end_time else "??"
    time_range = f"{start} - {end}"

    # Build the display
    col1, col2 = st.columns([3, 1])

    with col1:
        # Main line: time + block type + project/task
        block_label = block.block_type.value.replace("_", " ").title()
        st.markdown(f"{icon} **{time_range}** · {block_label}")

        # Details line
        details = []
        if block.project_name:
            details.append(f"[{block.project_name}]")
        if block.task_title:
            details.append(block.task_title)

        if details:
            st.caption(" — ".join(details))

    with col2:
        st.caption(f"{status_badge} {block.status}")


# ---------------------------------------------------------------------------
# Section 5: Insights Feed
# ---------------------------------------------------------------------------

def render_insights_feed():
    """Render recent AI-generated insights."""
    st.subheader("💡 Insights")

    # Get recent insights (only 'new' and 'seen', not dismissed)
    insights = get_recent_insights(limit=8, status=None)
    insights = [i for i in insights if i.status in ("new", "seen")]

    if not insights:
        st.caption("No recent insights. They'll appear after your first briefing or analysis.")
        return

    # Render each insight
    for insight in insights:
        _render_insight_card(insight)


def _render_insight_card(insight: Insight):
    """Render a single insight card."""
    # Severity icons
    severity_icons = {
        "info": "ℹ️",
        "warning": "⚠️",
        "action_required": "🚨"
    }
    icon = severity_icons.get(insight.severity.value, "ℹ️")

    # Type badge
    type_colors = {
        "priority": "🎯",
        "dependency": "🔗",
        "pattern": "📈",
        "recommendation": "💡",
        "alert": "🔔",
        "coaching": "🎓"
    }
    type_badge = type_colors.get(insight.type.value, "💡")

    # Render the insight
    with st.container():
        st.markdown(f"{icon} {type_badge} **{insight.type.value.replace('_', ' ').title()}**")

        # Truncate long insights for feed view
        content = insight.content
        if len(content) > 200:
            content = content[:200] + "..."

        st.caption(content)

        # Show timestamp
        if insight.created_at:
            st.caption(f"Generated {insight.created_at}")

        st.divider()


# ---------------------------------------------------------------------------
# Main Dashboard Renderer
# ---------------------------------------------------------------------------

def render_dashboard():
    """Render the complete dashboard with all sections."""
    st.header("📊 Dashboard")

    # Section 0: Morning Briefing
    render_morning_briefing()
    st.divider()

    # Section 1: Today's Focus
    render_todays_focus()
    st.divider()

    # Section 2: Project Cards
    render_project_cards()
    st.divider()

    # Section 3: Recent Knowledge
    render_recent_knowledge()
    st.divider()

    # Section 4: Today's Schedule
    render_todays_schedule()
    st.divider()

    # Section 5: Insights Feed
    render_insights_feed()
