#!/usr/bin/env python3
"""CLI test script for Iuxis Day 1 components.
Tests: DB, project/task CRUD, Obsidian reader, and Claude API.

Run: python tests/test_cli.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_database():
    section("1. Database Initialization")
    from iuxis.db import init_db, get_db_path
    init_db()
    print(f"  DB path: {get_db_path()}")
    print("  ✅ Database ready")


def test_projects():
    section("2. Project CRUD")
    from iuxis.project_manager import (
        create_project, get_project, list_projects,
        update_project, get_all_projects_summary,
    )

    # Create
    p = create_project(
        name="Test Project Alpha",
        type="product",
        priority=2,
        description="A test project",
        time_allocation_hrs_week=5.0,
        current_focus="Testing the CRUD layer",
    )
    print(f"  Created: #{p.id} — {p.name}")

    # Read
    p2 = get_project(p.id)
    assert p2 is not None
    assert p2.name == "Test Project Alpha"
    print(f"  Read: #{p2.id} — {p2.name} (priority={p2.priority})")

    # Update
    p3 = update_project(p.id, priority=1, current_focus="Updated focus")
    assert p3.priority == 1
    print(f"  Updated: priority={p3.priority}, focus={p3.current_focus}")

    # List
    all_projects = list_projects()
    print(f"  List: {len(all_projects)} project(s)")

    # Summary
    summary = get_all_projects_summary()
    print(f"  Summary:\n{summary}")
    print("  ✅ Project CRUD working")


def test_tasks():
    section("3. Task CRUD")
    from iuxis.task_manager import (
        create_task, get_task, list_tasks, update_task,
        complete_task, get_todays_tasks, get_all_tasks_summary,
    )
    from iuxis.project_manager import list_projects

    projects = list_projects()
    pid = projects[0].id if projects else None

    # Create
    t = create_task(
        title="Write unit tests",
        project_id=pid,
        priority=1,
        due_date=date.today(),
        estimated_hours=2.0,
    )
    print(f"  Created: #{t.id} — {t.title}")

    t2 = create_task(
        title="Review architecture doc",
        project_id=pid,
        priority=2,
        due_date=date.today() + timedelta(days=3),
        estimated_hours=1.5,
    )
    print(f"  Created: #{t2.id} — {t2.title}")

    # Update
    t3 = update_task(t.id, status="in_progress")
    assert t3.status.value == "in_progress"
    print(f"  Updated: #{t3.id} status → {t3.status.value}")

    # Complete
    t4 = complete_task(t.id)
    assert t4.status.value == "done"
    print(f"  Completed: #{t4.id} → {t4.status.value}")

    # Today's tasks
    todays = get_todays_tasks()
    print(f"  Today's tasks: {len(todays)}")

    # Summary
    summary = get_all_tasks_summary()
    print(f"  Summary:\n{summary}")
    print("  ✅ Task CRUD working")


def test_obsidian():
    section("4. Obsidian Vault Reader")
    from iuxis.obsidian import get_vault_path, index_vault, search_vault, get_vault_stats

    vault = get_vault_path()
    print(f"  Vault path: {vault}")

    if not vault.exists():
        print(f"  ⚠️  Vault not found at {vault} — skipping indexing")
        print("  Update vault_path in config.yaml to enable")
        return

    count = index_vault(verbose=True)
    stats = get_vault_stats()
    print(f"  Stats: {stats}")

    # Test search
    results = search_vault(keywords=["health"])
    print(f"  Search 'health': {len(results)} result(s)")
    for r in results[:3]:
        print(f"    📄 {r['file_name']}")

    print("  ✅ Obsidian reader working")


def test_claude_api():
    section("5. Claude API Client")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ⚠️  ANTHROPIC_API_KEY not set — skipping API test")
        print("  Set it and re-run to test Claude integration")
        return

    from iuxis.claude_client import chat

    print("  Sending test query to Claude...")
    response, tokens = chat("Hello, confirm you are the Chief of Staff. Reply in one sentence.")
    print(f"  Response: {response[:200]}")
    print(f"  Tokens used: {tokens}")
    print("  ✅ Claude API working")


def test_chat_handler():
    section("6. Chat Handler (Action Parsing)")
    from iuxis.chat_handler import parse_actions, execute_action

    # Test action parsing
    test_response = '''Here's what I'll do:

```json
{"action": "create_task", "params": {"title": "Test action task", "priority": 2}}
```

Done!'''

    actions = parse_actions(test_response)
    print(f"  Parsed {len(actions)} action(s) from response")
    for a in actions:
        print(f"    Action: {a['action']} — {a['params']}")
        result = execute_action(a)
        print(f"    Result: {result}")

    print("  ✅ Chat handler working")


if __name__ == "__main__":
    print("\n" + "═"*60)
    print("  Iuxis Day 1 — Component Test Suite")
    print("═"*60)

    test_database()
    test_projects()
    test_tasks()
    test_obsidian()
    test_claude_api()
    test_chat_handler()

    section("All Tests Complete ✅")
    print("  Next step: Run the seed data script:")
    print("    python -m iuxis.seed_data")
    print()
    print("  Then start the app (Day 2):")
    print("    streamlit run app.py")
    print()
