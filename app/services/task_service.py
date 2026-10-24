"""任务 CRUD 与筛选（纯本地 SQLite，操作快，UI 线程直接调用）。"""
from contextlib import closing
from datetime import date, datetime, timedelta
from typing import Optional

from app.core.db import get_connection
from app.models.task import Task

_COLS = ("id, title, description, status, priority, due_date, tags, repo_id, "
         "issue_number, issue_url, synced_at, completed_at, created_at, updated_at")

_ORDER = """
ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
         CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END,
         due_date ASC, id DESC
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def list_tasks(status: Optional[str] = None, repo_id: Optional[int] = None,
               search: str = "", priority: Optional[str] = None,
               tag: Optional[str] = None, due: str = "all") -> list[Task]:
    """按状态/仓库/关键字/优先级/标签/截止日综合筛选，优先级 + 到期日排序。"""
    sql = f"SELECT {_COLS} FROM tasks"
    conds: list[str] = []
    params: list = []
    if status:
        conds.append("status = ?")
        params.append(status)
    if repo_id:
        conds.append("repo_id = ?")
        params.append(repo_id)
    if priority:
        conds.append("priority = ?")
        params.append(priority)
    if search.strip():
        like = f"%{search.strip()}%"
        conds.append("(title LIKE ? OR description LIKE ? OR tags LIKE ?)")
        params += [like, like, like]
    if tag:
        conds.append("(',' || REPLACE(tags, ' ', '') || ',') LIKE ?")
        params.append(f"%,{tag.strip()},%")
    today = date.today()
    if due == "today":
        conds.append("due_date = ?")
        params.append(today.isoformat())
    elif due == "overdue":
        conds.append("due_date IS NOT NULL AND due_date != '' AND due_date < ? AND status != 'done'")
        params.append(today.isoformat())
    elif due == "week":
        conds.append("due_date >= ? AND due_date <= ?")
        params += [today.isoformat(), (today + timedelta(days=7)).isoformat()]
    elif due == "none":
        conds.append("(due_date IS NULL OR due_date = '')")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += _ORDER
    with closing(get_connection()) as conn:
        return [Task.from_row(r) for r in conn.execute(sql, params).fetchall()]


def get_task(task_id: int) -> Optional[Task]:
    with closing(get_connection()) as conn:
        row = conn.execute(f"SELECT {_COLS} FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return Task.from_row(row) if row else None


def create_task(task: Task) -> int:
    """插入任务，返回新 id；完成态任务自动补完成时间。"""
    now = _now()
    if task.status == "done" and not task.completed_at:
        task.completed_at = now
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, description, status, priority, due_date, tags, repo_id, "
            "issue_number, issue_url, synced_at, completed_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task.title, task.description, task.status, task.priority, task.due_date,
             task.tags, task.repo_id, task.issue_number, task.issue_url, task.synced_at,
             task.completed_at, now, now),
        )
        conn.commit()
        return cur.lastrowid


def update_task(task: Task) -> None:
    """全量更新；状态变化时维护完成时间（离开完成态清空）。"""
    if task.status == "done" and not task.completed_at:
        task.completed_at = _now()
    elif task.status != "done":
        task.completed_at = None
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE tasks SET title=?, description=?, status=?, priority=?, due_date=?, tags=?, "
            "repo_id=?, issue_number=?, issue_url=?, synced_at=?, completed_at=?, updated_at=? "
            "WHERE id=?",
            (task.title, task.description, task.status, task.priority, task.due_date,
             task.tags, task.repo_id, task.issue_number, task.issue_url, task.synced_at,
             task.completed_at, _now(), task.id),
        )
        conn.commit()


def move_task(task_id: int, new_status: str) -> None:
    """改变任务状态（按钮、右键、跨列拖拽统一入口）。"""
    now = _now()
    with closing(get_connection()) as conn:
        if new_status == "done":
            conn.execute(
                "UPDATE tasks SET status=?, completed_at=COALESCE(completed_at, ?), updated_at=? "
                "WHERE id=?", (new_status, now, now, task_id))
        else:
            conn.execute(
                "UPDATE tasks SET status=?, completed_at=NULL, updated_at=? WHERE id=?",
                (new_status, now, task_id))
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


def all_tags() -> list[str]:
    """已使用过的标签（按出现次数降序）。"""
    counts: dict[str, int] = {}
    with closing(get_connection()) as conn:
        for row in conn.execute("SELECT tags FROM tasks WHERE tags != ''").fetchall():
            for t in (row["tags"] or "").split(","):
                t = t.strip()
                if t:
                    counts[t] = counts.get(t, 0) + 1
    return [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
