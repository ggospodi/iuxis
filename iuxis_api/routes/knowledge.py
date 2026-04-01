"""Knowledge base endpoints."""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from pydantic import BaseModel
from iuxis_api.deps import get_db
from iuxis import knowledge_manager

router = APIRouter()

@router.get("")
def list_knowledge(
    project_id: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 50,
    db=Depends(get_db)
):
    """Get knowledge entries with filters."""
    query = """
        SELECT uk.id, uk.category, uk.content, uk.source_file, uk.confidence,
               uk.relevance_tags, uk.status, uk.created_at, p.name as project_name, p.id as project_id
        FROM user_knowledge uk
        LEFT JOIN projects p ON uk.project_id = p.id
        WHERE uk.status = 'approved'
    """
    params = []

    if project_id:
        query += " AND uk.project_id = ?"
        params.append(project_id)
    if category:
        query += " AND uk.category = ?"
        params.append(category)

    query += " ORDER BY uk.created_at DESC LIMIT ?"
    params.append(limit)

    cursor = db.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    entries = [dict(zip(columns, row)) for row in rows]

    return {"entries": entries, "total": len(entries)}

@router.get("/search")
def search_knowledge_endpoint(
    q: str = Query(..., description="Search query"),
    mode: str = Query("hybrid", description="semantic | sql | hybrid"),
    limit: int = Query(10, ge=1, le=50),
    project_id: Optional[int] = Query(None),
    db=Depends(get_db)
):
    """
    Search knowledge entries.
    mode=hybrid (default): semantic + SQL merged, importance-ranked
    mode=semantic: FAISS only
    mode=sql: existing SQL path only
    """
    if not q.strip():
        return {"results": [], "count": 0, "mode": mode}

    if mode == "semantic":
        results = knowledge_manager.search_semantic(q, topk=limit)
    elif mode == "sql":
        # SQL-only fallback using existing logic
        query = """
            SELECT uk.id, uk.category, uk.content, uk.source_file, uk.confidence,
                   uk.created_at, uk.importance, uk.pinned, p.name as project_name
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            WHERE uk.status = 'approved' AND uk.content LIKE ?
        """
        params = [f"%{q}%"]

        if project_id:
            query += " AND uk.project_id = ?"
            params.append(project_id)

        query += " ORDER BY uk.created_at DESC LIMIT ?"
        params.append(limit)

        cursor = db.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        results = [dict(zip(columns, row)) for row in rows]
    else:  # hybrid (default)
        results = knowledge_manager.search_hybrid(q, project_id=project_id, topk=limit)

    return {
        "results": results,
        "count": len(results),
        "mode": mode,
        "query": q
    }


@router.post("/{entry_id}/pin")
def pin_knowledge_entry(entry_id: int):
    """Pin a knowledge entry — marks it highest priority in context assembly."""
    success = knowledge_manager.pin_entry(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"pinned": True, "entry_id": entry_id}

@router.get("/stats")
def knowledge_stats(db=Depends(get_db)):
    """Knowledge entry counts per project."""
    rows = db.execute("""
        SELECT p.name, p.id, COUNT(uk.id) as count,
               GROUP_CONCAT(DISTINCT uk.category) as categories
        FROM user_knowledge uk
        LEFT JOIN projects p ON uk.project_id = p.id
        WHERE uk.status = 'approved'
        GROUP BY uk.project_id
        ORDER BY count DESC
    """).fetchall()

    total = sum(r[2] for r in rows)
    stats = [{"project_name": r[0] or "General", "project_id": r[1],
              "count": r[2], "categories": r[3]} for r in rows]

    return {"stats": stats, "total_entries": total, "total_projects": len(stats)}

@router.get("/graph")
def knowledge_graph(
    project_id: Optional[int] = Query(None, description="Filter by project ID"),
    relationship_type: Optional[str] = Query(None, description="Filter by relationship type"),
    min_confidence: Optional[str] = Query(None, description="Minimum confidence: high/medium/low"),
    db=Depends(get_db)
):
    """
    Get knowledge graph with nodes and edges.

    Returns only entries that have at least one relationship, along with their connections.
    """
    # Build query for edges (relationships)
    edges_query = """
        SELECT kr.source_entry_id as from_id, kr.target_entry_id as to_id,
               kr.relation_type as relationship_type, kr.confidence
        FROM knowledge_relations kr
        WHERE 1=1
    """
    edges_params = []

    # Apply filters
    if project_id is not None:
        # Filter edges where either source or target is from the specified project
        edges_query += """ AND (
            EXISTS (SELECT 1 FROM user_knowledge WHERE id = kr.source_entry_id AND project_id = ?)
            OR EXISTS (SELECT 1 FROM user_knowledge WHERE id = kr.target_entry_id AND project_id = ?)
        )"""
        edges_params.extend([project_id, project_id])

    if relationship_type:
        edges_query += " AND kr.relation_type = ?"
        edges_params.append(relationship_type)

    if min_confidence:
        # Filter by confidence level
        confidence_levels = {"high": ["high"], "medium": ["high", "medium"], "low": ["high", "medium", "low"]}
        allowed_confidences = confidence_levels.get(min_confidence.lower(), ["high", "medium", "low"])
        placeholders = ",".join(["?"] * len(allowed_confidences))
        edges_query += f" AND kr.confidence IN ({placeholders})"
        edges_params.extend(allowed_confidences)

    # Fetch edges
    cursor = db.execute(edges_query, edges_params)
    edges_columns = [desc[0] for desc in cursor.description]
    edges_rows = cursor.fetchall()
    edges = [dict(zip(edges_columns, row)) for row in edges_rows]

    # Get unique node IDs from edges
    node_ids = set()
    for edge in edges:
        node_ids.add(edge["from_id"])
        node_ids.add(edge["to_id"])

    # Fetch node details
    nodes = []
    if node_ids:
        placeholders = ",".join(["?"] * len(node_ids))
        nodes_query = f"""
            SELECT uk.id, uk.content, uk.category, uk.project_id,
                   uk.importance, p.name as project_name
            FROM user_knowledge uk
            LEFT JOIN projects p ON uk.project_id = p.id
            WHERE uk.id IN ({placeholders})
        """
        cursor = db.execute(nodes_query, list(node_ids))
        nodes_columns = [desc[0] for desc in cursor.description]
        nodes_rows = cursor.fetchall()
        nodes = [dict(zip(nodes_columns, row)) for row in nodes_rows]

    # Calculate statistics
    relationship_counts = {}
    for edge in edges:
        rel_type = edge["relationship_type"]
        relationship_counts[rel_type] = relationship_counts.get(rel_type, 0) + 1

    stats = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "relationship_counts": relationship_counts
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": stats
    }

@router.get("/unassigned")
def get_unassigned_entries(db=Depends(get_db)):
    """Get all knowledge entries where project_id IS NULL (unassigned inbox queue)."""
    query = """
        SELECT uk.id, uk.category, uk.content, uk.source_file, uk.confidence,
               uk.relevance_tags, uk.status, uk.created_at, p.name as project_name, p.id as project_id
        FROM user_knowledge uk
        LEFT JOIN projects p ON uk.project_id = p.id
        WHERE uk.project_id IS NULL
        ORDER BY uk.created_at DESC
    """
    cursor = db.execute(query)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    entries = [dict(zip(columns, row)) for row in rows]

    return {"entries": entries, "total": len(entries)}

class AssignRequest(BaseModel):
    project_id: int

@router.post("/{entry_id}/assign")
def assign_entry(entry_id: int, body: AssignRequest, db=Depends(get_db)):
    """Assign an unassigned knowledge entry to a project."""
    # Verify entry exists
    entry = db.execute("SELECT id FROM user_knowledge WHERE id = ?", [entry_id]).fetchone()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Update project_id
    db.execute("UPDATE user_knowledge SET project_id = ? WHERE id = ?", [body.project_id, entry_id])
    db.commit()

    return {"status": "ok", "entry_id": entry_id, "project_id": body.project_id}
