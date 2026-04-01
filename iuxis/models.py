"""Data models for Iuxis entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time
from enum import Enum
from typing import Optional
import json


# --- Enums ---

class ProjectType(str, Enum):
    COMPANY = "company"
    PRODUCT = "product"
    RESEARCH = "research"
    LEARNING = "learning"
    ADVISORY = "advisory"
    CONSULTING = "consulting"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    MONITORING = "monitoring"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class BlockType(str, Enum):
    DEEP_WORK = "deep_work"
    ADMIN = "admin"
    MEETING = "meeting"
    BREAK = "break"
    REVIEW = "review"


class InsightType(str, Enum):
    PRIORITY = "priority"
    DEPENDENCY = "dependency"
    PATTERN = "pattern"
    RECOMMENDATION = "recommendation"
    ALERT = "alert"
    COACHING = "coaching"


class InsightSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ACTION_REQUIRED = "action_required"


# --- Dataclasses ---

@dataclass
class Project:
    id: Optional[int] = None
    parent_id: Optional[int] = None
    name: str = ""
    type: ProjectType = ProjectType.PRODUCT
    status: ProjectStatus = ProjectStatus.ACTIVE
    priority: int = 3
    description: str = ""
    time_allocation_hrs_week: float = 0.0
    current_focus: str = ""
    obsidian_folder: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def tags_json(self) -> str:
        return json.dumps(self.tags)

    @classmethod
    def from_row(cls, row: dict) -> Project:
        tags = json.loads(row.get("tags") or "[]")
        return cls(
            id=row["id"],
            parent_id=row.get("parent_id"),
            name=row["name"],
            type=ProjectType(row["type"]) if row.get("type") else ProjectType.PRODUCT,
            status=ProjectStatus(row["status"]) if row.get("status") else ProjectStatus.ACTIVE,
            priority=row.get("priority", 3),
            description=row.get("description", ""),
            time_allocation_hrs_week=row.get("time_allocation_hrs_week", 0.0),
            current_focus=row.get("current_focus", ""),
            obsidian_folder=row.get("obsidian_folder", ""),
            tags=tags,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def summary(self) -> str:
        """One-line summary for Claude context."""
        status_icon = {
            "active": "🟢", "paused": "⏸️", "blocked": "🔴", "monitoring": "👁️"
        }.get(self.status.value, "⚪")
        parent_str = f" (sub of #{self.parent_id})" if self.parent_id else ""
        return (
            f"[P{self.priority}] {status_icon} {self.name}{parent_str} "
            f"({self.type.value}) — {self.current_focus or self.description or 'No focus set'} "
            f"[{self.time_allocation_hrs_week}h/wk]"
        )


@dataclass
class Task:
    id: Optional[int] = None
    project_id: Optional[int] = None
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: int = 3
    due_date: Optional[date] = None
    estimated_hours: Optional[float] = None
    actual_hours: float = 0.0
    created_by: str = "user"
    ai_rationale: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Joined field (not in DB)
    project_name: str = ""

    @property
    def tags_json(self) -> str:
        return json.dumps(self.tags)

    @classmethod
    def from_row(cls, row: dict) -> Task:
        tags = json.loads(row.get("tags") or "[]")
        due = row.get("due_date")
        if isinstance(due, str) and due:
            due = date.fromisoformat(due)
        return cls(
            id=row["id"],
            project_id=row.get("project_id"),
            title=row["title"],
            description=row.get("description", ""),
            status=TaskStatus(row["status"]) if row.get("status") else TaskStatus.TODO,
            priority=row.get("priority", 3),
            due_date=due,
            estimated_hours=row.get("estimated_hours"),
            actual_hours=row.get("actual_hours", 0.0),
            created_by=row.get("created_by", "user"),
            ai_rationale=row.get("ai_rationale", ""),
            tags=tags,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            completed_at=row.get("completed_at"),
            project_name=row.get("project_name", ""),
        )

    def summary(self) -> str:
        status_icon = {
            "todo": "⬜", "in_progress": "🔵", "blocked": "🔴", "done": "✅", "cancelled": "❌"
        }.get(self.status.value, "⬜")
        due_str = f" due:{self.due_date}" if self.due_date else ""
        est_str = f" ~{self.estimated_hours}h" if self.estimated_hours else ""
        return f"[P{self.priority}] {status_icon} {self.title}{due_str}{est_str}"


@dataclass
class Insight:
    id: Optional[int] = None
    type: InsightType = InsightType.RECOMMENDATION
    content: str = ""
    related_project_ids: list[int] = field(default_factory=list)
    related_task_ids: list[int] = field(default_factory=list)
    severity: InsightSeverity = InsightSeverity.INFO
    status: str = "new"
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> Insight:
        return cls(
            id=row["id"],
            type=InsightType(row["type"]) if row.get("type") else InsightType.RECOMMENDATION,
            content=row["content"],
            related_project_ids=json.loads(row.get("related_project_ids") or "[]"),
            related_task_ids=json.loads(row.get("related_task_ids") or "[]"),
            severity=InsightSeverity(row["severity"]) if row.get("severity") else InsightSeverity.INFO,
            status=row.get("status", "new"),
            created_at=row.get("created_at"),
        )


@dataclass
class ScheduleBlock:
    id: Optional[int] = None
    date: Optional[date] = None
    project_id: Optional[int] = None
    task_id: Optional[int] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    block_type: BlockType = BlockType.DEEP_WORK
    status: str = "planned"
    created_at: Optional[datetime] = None

    # Joined fields
    project_name: str = ""
    task_title: str = ""

    @classmethod
    def from_row(cls, row: dict) -> ScheduleBlock:
        st = row.get("start_time")
        et = row.get("end_time")
        d = row.get("date")
        if isinstance(st, str) and st:
            st = time.fromisoformat(st)
        if isinstance(et, str) and et:
            et = time.fromisoformat(et)
        if isinstance(d, str) and d:
            d = date.fromisoformat(d)
        return cls(
            id=row["id"],
            date=d,
            project_id=row.get("project_id"),
            task_id=row.get("task_id"),
            start_time=st,
            end_time=et,
            block_type=BlockType(row["block_type"]) if row.get("block_type") else BlockType.DEEP_WORK,
            status=row.get("status", "planned"),
            created_at=row.get("created_at"),
            project_name=row.get("project_name", ""),
            task_title=row.get("task_title", ""),
        )


@dataclass
class ChatMessage:
    id: Optional[int] = None
    role: str = "user"
    content: str = ""
    tokens_used: int = 0
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> ChatMessage:
        return cls(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            tokens_used=row.get("tokens_used", 0),
            created_at=row.get("created_at"),
        )


@dataclass
class VaultFile:
    id: Optional[int] = None
    file_path: str = ""
    file_name: str = ""
    file_type: str = "md"
    frontmatter: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    last_modified: Optional[datetime] = None
    indexed_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> VaultFile:
        return cls(
            id=row["id"],
            file_path=row["file_path"],
            file_name=row["file_name"],
            file_type=row.get("file_type", "md"),
            frontmatter=json.loads(row.get("frontmatter") or "{}"),
            tags=json.loads(row.get("tags") or "[]"),
            last_modified=row.get("last_modified"),
            indexed_at=row.get("indexed_at"),
        )
