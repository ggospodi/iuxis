"""Obsidian vault reader — indexing, search, and content extraction."""
from __future__ import annotations

import os
import json
from pathlib import Path
from datetime import datetime, date
from typing import Optional

import frontmatter

from iuxis.db import load_config, db_session, fetch_all, execute, log_activity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


def get_vault_path() -> Path:
    cfg = load_config()
    return _expand(cfg["obsidian"]["vault_path"])


def get_pdf_folders() -> list[Path]:
    cfg = load_config()
    return [_expand(p) for p in cfg["obsidian"].get("pdf_folders", [])]


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def index_vault(verbose: bool = False) -> int:
    """Walk the vault and index all markdown files + PDFs into vault_index.
    Returns number of files indexed."""
    vault = get_vault_path()
    if not vault.exists():
        print(f"⚠️  Vault not found: {vault}")
        return 0

    count = 0

    # Markdown files
    for md_file in vault.rglob("*.md"):
        # Skip hidden dirs (e.g., .obsidian, .trash)
        if any(part.startswith(".") for part in md_file.relative_to(vault).parts):
            continue
        _index_md_file(md_file, vault)
        count += 1

    # PDF files
    for pdf_dir in get_pdf_folders():
        if not pdf_dir.exists():
            continue
        for pdf_file in pdf_dir.rglob("*.pdf"):
            _index_pdf_file(pdf_file)
            count += 1

    if verbose:
        print(f"✓ Indexed {count} files from vault")
    log_activity("obsidian_pull", f"Indexed {count} files")
    return count


def _json_serial(obj):
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, '__str__'):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _index_md_file(path: Path, vault_root: Path) -> None:
    """Parse and index a single markdown file."""
    try:
        post = frontmatter.load(str(path))
        fm = dict(post.metadata) if post.metadata else {}
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
    except Exception:
        fm = {}
        tags = []

    mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()

    execute(
        """INSERT INTO vault_index (file_path, file_name, file_type, frontmatter, tags, last_modified, indexed_at)
           VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(file_path) DO UPDATE SET
             frontmatter = excluded.frontmatter,
             tags = excluded.tags,
             last_modified = excluded.last_modified,
             indexed_at = CURRENT_TIMESTAMP""",
        (str(path), path.name, "md", json.dumps(fm, default=_json_serial), json.dumps(tags, default=_json_serial), mtime),
    )


def _index_pdf_file(path: Path) -> None:
    mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    execute(
        """INSERT INTO vault_index (file_path, file_name, file_type, frontmatter, tags, last_modified, indexed_at)
           VALUES (?, ?, ?, '{}', '[]', ?, CURRENT_TIMESTAMP)
           ON CONFLICT(file_path) DO UPDATE SET
             last_modified = excluded.last_modified,
             indexed_at = CURRENT_TIMESTAMP""",
        (str(path), path.name, "pdf", mtime),
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_vault(
    keywords: Optional[list[str]] = None,
    folder: Optional[str] = None,
    tags: Optional[list[str]] = None,
    file_type: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Search the vault index. Returns list of matching file metadata."""
    query = "SELECT * FROM vault_index WHERE 1=1"
    params: list = []

    if file_type:
        query += " AND file_type = ?"
        params.append(file_type)

    if folder:
        query += " AND file_path LIKE ?"
        params.append(f"%{folder}%")

    if tags:
        for tag in tags:
            query += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')

    if keywords:
        for kw in keywords:
            query += " AND (file_name LIKE ? OR frontmatter LIKE ?)"
            params.extend([f"%{kw}%", f"%{kw}%"])

    query += f" ORDER BY last_modified DESC LIMIT {limit}"
    return fetch_all(query, tuple(params))


def search_vault_content(
    query_terms: list[str],
    folder: Optional[str] = None,
    max_files: int = 10,
    max_chars_per_file: int = 3000,
) -> list[dict]:
    """Full-text search inside vault markdown files.
    Returns list of {file_path, file_name, snippet} dicts."""
    vault = get_vault_path()
    if not vault.exists():
        return []

    results = []
    search_root = vault / folder if folder else vault

    if not search_root.exists():
        return []

    for md_file in search_root.rglob("*.md"):
        if any(part.startswith(".") for part in md_file.relative_to(vault).parts):
            continue
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            content_lower = content.lower()
            if any(term.lower() in content_lower for term in query_terms):
                # Extract relevant snippet
                snippet = _extract_snippet(content, query_terms, max_chars_per_file)
                results.append({
                    "file_path": str(md_file),
                    "file_name": md_file.name,
                    "snippet": snippet,
                })
                if len(results) >= max_files:
                    break
        except Exception:
            continue

    log_activity("obsidian_pull", f"Content search: {query_terms}, found {len(results)} files")
    return results


def _extract_snippet(content: str, terms: list[str], max_chars: int) -> str:
    """Extract a relevant snippet around the first matching term."""
    content_lower = content.lower()
    best_pos = len(content)

    for term in terms:
        pos = content_lower.find(term.lower())
        if 0 <= pos < best_pos:
            best_pos = pos

    # Window around the match
    start = max(0, best_pos - 200)
    end = min(len(content), start + max_chars)
    snippet = content[start:end]

    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet


def read_file_content(file_path: str, max_chars: int = 5000) -> str:
    """Read full content of a vault file (markdown or PDF)."""
    path = Path(file_path)

    if not path.exists():
        return f"File not found: {file_path}"

    if path.suffix.lower() == ".pdf":
        return _read_pdf(path, max_chars)

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            return content[:max_chars] + f"\n\n... [truncated, {len(content)} chars total]"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def _read_pdf(path: Path, max_chars: int) -> str:
    """Extract text from a PDF file."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        text_parts = []
        total = 0
        for page in doc:
            page_text = page.get_text()
            text_parts.append(page_text)
            total += len(page_text)
            if total > max_chars:
                break
        doc.close()
        full = "\n".join(text_parts)
        if len(full) > max_chars:
            return full[:max_chars] + f"\n\n... [truncated, {len(full)} chars total]"
        return full
    except ImportError:
        return "PyMuPDF not installed. Run: pip install PyMuPDF"
    except Exception as e:
        return f"Error reading PDF: {e}"


def get_vault_stats() -> dict:
    """Quick stats about the indexed vault."""
    rows = fetch_all("SELECT file_type, COUNT(*) as cnt FROM vault_index GROUP BY file_type")
    stats = {r["file_type"]: r["cnt"] for r in rows}
    stats["total"] = sum(stats.values())
    return stats
