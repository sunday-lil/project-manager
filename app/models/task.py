"""任务数据模型。"""
from dataclasses import dataclass
from typing import Optional, Any


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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "Task":
        return cls(**dict(row))
