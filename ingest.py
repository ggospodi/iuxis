#!/usr/bin/env python3
"""
Iuxis Ingestion Engine — CLI

Drop files into projects/<slug>/raw/ and run this to process them.

Usage:
    python ingest.py <slug>                  Ingest new files for a project
    python ingest.py --all                   Ingest all projects with new files
    python ingest.py <slug> --dry-run        Show what would be processed
    python ingest.py <slug> --force          Re-process all files (ignore manifest)
    python ingest.py --init "Project Name"   Initialize a new project folder
    python ingest.py --migrate               Migrate existing checkpoints to new structure
    python ingest.py --stats                 Show knowledge base statistics
    python ingest.py --query <slug> "text"   Search knowledge base for a project
    python ingest.py --pending               Show projects with unprocessed files

Examples:
    python ingest.py novabrew
    python ingest.py orbit-marketing --dry-run
    python ingest.py --init "Voxgenius"
    python ingest.py --all
    python ingest.py --query novabrew "quarterly review"
"""

import sys
import os

# Add project root to path so we can import iuxis package
sys.path.insert(0, os.path.expanduser("~/Desktop/iuxis"))

from iuxis.ingestion_engine import (
    ingest_project,
    ingest_all,
    init_project,
    migrate_existing_checkpoints,
    scan_for_new_files,
    load_manifest,
    resolve_project,
    PROJECTS_DIR,
)
from iuxis.knowledge_manager import (
    search_knowledge,
    get_knowledge_stats,
    format_stats,
)


def cmd_ingest(slug: str, force: bool = False, dry_run: bool = False):
    """Ingest new files for a specific project."""
    print(f"\n🔄 Ingesting: {slug}")
    result = ingest_project(slug, force=force, dry_run=dry_run)

    if result.get("error"):
        print(f"\n❌ Error: {result['error']}")
    elif result.get("dry_run"):
        print(f"\n🔍 Dry run complete — {result.get('files_found', 0)} files would be processed")
    elif result.get("files_processed", 0) == 0:
        print(f"\n✅ No new files to process for {result.get('project', slug)}")
    else:
        print(f"\n✅ Ingestion complete for {result.get('project', slug)}:")
        print(f"   Files processed: {result.get('files_processed', 0)}")
        print(f"   Knowledge added: {result.get('knowledge_added', 0)}")
        print(f"   Tasks created: {result.get('tasks_created', 0)}")
        print(f"   Tasks updated: {result.get('tasks_updated', 0)}")
        print(f"   Insights added: {result.get('insights_added', 0)}")


def cmd_ingest_all(force: bool = False, dry_run: bool = False):
    """Ingest all projects with new files."""
    print("\n🔄 Ingesting all projects...")
    results = ingest_all(force=force, dry_run=dry_run)

    if not results:
        print("\n⚠️ No projects found or no projects directory.")
        return

    total_files = sum(r.get("files_processed", 0) for r in results)
    total_knowledge = sum(r.get("knowledge_added", 0) for r in results)
    total_tasks = sum(r.get("tasks_created", 0) for r in results)

    print(f"\n{'='*50}")
    print(f"✅ Ingestion complete:")
    print(f"   Projects processed: {len(results)}")
    print(f"   Total files: {total_files}")
    print(f"   Total knowledge entries: {total_knowledge}")
    print(f"   Total tasks created: {total_tasks}")


def cmd_init(name: str):
    """Initialize a new project folder."""
    print(f"\n📁 Initializing project: {name}")
    slug = init_project(name)
    print(f"\n✅ Project initialized:")
    print(f"   Folder: {PROJECTS_DIR}/{slug}/")
    print(f"   Drop files into: {PROJECTS_DIR}/{slug}/raw/")
    print(f"   Then run: python ingest.py {slug}")


def cmd_migrate():
    """Migrate existing checkpoints."""
    print("\n📦 Migrating existing checkpoints to projects/ structure...")
    migrate_existing_checkpoints()


def cmd_stats():
    """Show knowledge base statistics."""
    stats = get_knowledge_stats()
    print(f"\n{format_stats(stats)}")


def cmd_query(slug: str, query_text: str):
    """Search the knowledge base for a project."""
    project = resolve_project(slug)
    project_id = project["id"] if project else None

    if not project:
        print(f"⚠️ No project found for '{slug}' — searching all projects")

    results = search_knowledge(query_text, project_id=project_id, limit=10)

    if not results:
        print(f"\n🔍 No results found for '{query_text}'")
        return

    print(f"\n🔍 Found {len(results)} result(s) for '{query_text}':")
    for r in results:
        cat = r.get("category", "?")
        content = r.get("content", "")
        source = r.get("source_file", "")
        date = r.get("created_at", "")[:10]
        print(f"\n  [{cat.upper()}] {content}")
        if source:
            print(f"    Source: {source} | {date}")


def cmd_pending():
    """Show projects with unprocessed files."""
    if not os.path.exists(PROJECTS_DIR):
        print(f"❌ No projects directory at {PROJECTS_DIR}")
        return

    print(f"\n📋 Pending files by project:\n")
    total_pending = 0

    for entry in sorted(os.listdir(PROJECTS_DIR)):
        project_dir = os.path.join(PROJECTS_DIR, entry)
        raw_dir = os.path.join(project_dir, "raw")

        if os.path.isdir(project_dir) and os.path.exists(raw_dir):
            manifest = load_manifest(project_dir)
            new_files = scan_for_new_files(project_dir, manifest)

            if new_files:
                print(f"  📁 {entry}: {len(new_files)} new file(s)")
                for f in new_files:
                    print(f"     - {os.path.basename(f)}")
                total_pending += len(new_files)
            else:
                print(f"  ✅ {entry}: up to date")

    print(f"\n  Total pending: {total_pending} file(s)")


def print_usage():
    """Print usage instructions."""
    print(__doc__)


def main():
    args = sys.argv[1:]

    if not args:
        print_usage()
        return

    # Parse flags
    force = "--force" in args
    dry_run = "--dry-run" in args
    args = [a for a in args if a not in ("--force", "--dry-run")]

    if args[0] == "--all":
        cmd_ingest_all(force=force, dry_run=dry_run)

    elif args[0] == "--init":
        if len(args) < 2:
            print("❌ Usage: python ingest.py --init \"Project Name\"")
            return
        cmd_init(args[1])

    elif args[0] == "--migrate":
        cmd_migrate()

    elif args[0] == "--stats":
        cmd_stats()

    elif args[0] == "--query":
        if len(args) < 3:
            print("❌ Usage: python ingest.py --query <slug> \"search text\"")
            return
        cmd_query(args[1], " ".join(args[2:]))

    elif args[0] == "--pending":
        cmd_pending()

    elif args[0] == "--help" or args[0] == "-h":
        print_usage()

    else:
        # Treat first arg as project slug
        cmd_ingest(args[0], force=force, dry_run=dry_run)


if __name__ == "__main__":
    main()
