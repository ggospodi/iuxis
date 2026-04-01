"""GitHub scanner endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from iuxis_api.deps import get_db
from iuxis import github_scanner

router = APIRouter()


class TestGitHubRequest(BaseModel):
    """Request model for testing GitHub connection."""
    token: Optional[str] = None


class ScanRequest(BaseModel):
    """Request model for triggering a GitHub scan."""
    project_id: int
    repo: str
    backfill_days: int = 60


class UpdateProjectGitHubRequest(BaseModel):
    """Request model for updating project GitHub repo."""
    github_repo: Optional[str] = None


@router.get("/status")
def get_github_status(db=Depends(get_db)):
    """Get GitHub scan status for all configured projects.

    Returns:
        - token_available: Whether GitHub PAT is configured
        - projects: List of projects with GitHub repos and scan status
    """
    status = github_scanner.get_scan_status()
    return status


@router.post("/test")
def test_github_connection(request: TestGitHubRequest):
    """Test GitHub API connection and return user info.

    If token is provided in request, temporarily saves it.
    Otherwise uses existing saved token.

    Returns:
        - success: Whether connection was successful
        - username: GitHub username (if success)
        - error: Error message (if failed)
    """
    # If token provided, save it first
    if request.token:
        try:
            github_scanner.save_github_token(request.token)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save token: {e}")

    # Test connection
    result = github_scanner.test_github_connection()

    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "Connection failed"))

    return result


@router.post("/scan")
def trigger_github_scan(request: ScanRequest, db=Depends(get_db)):
    """Trigger a manual GitHub scan for a project.

    Args:
        project_id: ID of the project to scan
        repo: Full repository name (e.g., 'owner/repo')
        backfill_days: Number of days of history to fetch (default 60)

    Returns:
        - commits: Number of commits ingested
        - issues: Number of issues/PRs ingested
        - branches: Number of branches ingested
    """
    # Verify project exists
    row = db.execute("SELECT id, name FROM projects WHERE id = ?", (request.project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Project {request.project_id} not found")

    # Update project's github_repo if not set
    db.execute(
        "UPDATE projects SET github_repo = ? WHERE id = ?",
        (request.repo, request.project_id)
    )
    db.commit()

    # Trigger scan
    try:
        results = github_scanner.scan_repository(
            project_id=request.project_id,
            repo=request.repo,
            backfill_days=request.backfill_days,
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")


@router.patch("/projects/{project_id}/github")
def update_project_github_repo(project_id: int, request: UpdateProjectGitHubRequest, db=Depends(get_db)):
    """Update GitHub repository for a project.

    Args:
        project_id: ID of the project to update
        github_repo: Full repository name (e.g., 'owner/repo') or None to unlink

    Returns:
        - success: Whether update was successful
    """
    # Verify project exists
    row = db.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Update github_repo
    db.execute(
        "UPDATE projects SET github_repo = ? WHERE id = ?",
        (request.github_repo, project_id)
    )
    db.commit()

    return {
        "success": True,
        "project_id": project_id,
        "github_repo": request.github_repo,
    }
