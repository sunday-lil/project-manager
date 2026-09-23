"""任务 CRUD（纯本地 SQLite，操作快，UI 线程直接调用）。"""
from contextlib import closing
from datetime import datetime
from typing import Optional

from app.core.db import get_connection
from app.models.task import Task

_COLS = ("id, title, description, status, priority, due_date, tags, repo_id, "
         "issue_number, issue_url, synced_at, created_at, updated_at")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def list_tasks(status: Optional[str] = None, repo_id: Optional[int] = None) -> list[Task]:
    """按状态/仓库过滤任务；不排序参数时按优先级+创建时间排。"""
    sql = f"SELECT {_COLS} FROM tasks"
    conds, params = [], []
    if status:
        conds.append("status = ?")
        params.append(status)
    if repo_id:
        conds.append("repo_id = ?")
        params.append(repo_id)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC"
    with closing(get_connection()) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [Task.from_row(r) for r in rows]


def get_task(task_id: int) -> Optional[Task]:
    with closing(get_connection()) as conn:
        row = conn.execute(f"SELECT {_COLS} FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return Task.from_row(row) if row else None


def create_task(task: Task) -> int:
    """插入任务，返回新 id。"""
    now = _now()
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, description, status, priority, due_date, tags, repo_id, "
            "issue_number, issue_url, synced_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task.title, task.description, task.status, task.priority, task.due_date,
             task.tags, task.repo_id, task.issue_number, task.issue_url, task.synced_at, now, now),
        )
        conn.commit()
        return cur.lastrowid


def update_task(task: Task) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE tasks SET title=?, description=?, status=?, priority=?, due_date=?, tags=?, "
            "repo_id=?, issue_number=?, issue_url=?, synced_at=?, updated_at=? WHERE id=?",
            (task.title, task.description, task.status, task.priority, task.due_date,
             task.tags, task.repo_id, task.issue_number, task.issue_url, task.synced_at,
             _now(), task.id),
        )
        conn.commit()


def move_task(task_id: int, new_status: str) -> None:
    """改变任务状态（按钮移动与跨列拖拽统一走此入口）。"""
    with closing(get_connection()) as conn:
        conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                     (new_status, _now(), task_id))
        conn.commit()


def delete_task(task_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()


def link_issue(task_id: int, issue_number: int, issue_url: str) -> None:
    """推送 Issue 成功后回写关联信息。"""
    with closing(get_connection()) as conn:
        conn.execute("UPDATE tasks SET issue_number=?, issue_url=?, synced_at=?, updated_at=? WHERE id=?",
                     (issue_number, issue_url, _now(), _now(), task_id))
        conn.commit()


def issue_numbers_of_repo(repo_id: int) -> set[int]:
    """某仓库已关联 issue 的编号集合，用于拉取时去重。"""
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT issue_number FROM tasks WHERE repo_id = ? AND issue_number IS NOT NULL",
            (repo_id,)).fetchall()
        return {r["issue_number"] for r in rows}
