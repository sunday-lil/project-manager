"""任务数据模型。"""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Task:
    id: Optional[int]
    title: str
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    due_date: Optional[str] = None
    tags: str = ""
    repo_id: Optional[int] = None
    issue_number: Optional[int] = None
    issue_url: Optional[str] = None
    synced_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def is_overdue(self) -> bool:
        from datetime import date
        return bool(self.due_date) and self.due_date < date.today().isoformat() \
            and self.status != "done"

    @classmethod
    def from_row(cls, row: Any) -> "Task":
        return cls(**dict(row))
