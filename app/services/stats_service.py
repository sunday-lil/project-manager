"""看板/工作台统计（只读查询）。"""
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.db import get_connection
from app.models.task import Task
from app.services.task_service import _COLS


@dataclass
class TaskStats:
    todo: int = 0
    doing: int = 0
    done: int = 0
    overdue: int = 0
    due_today: int = 0
    completed_week: int = 0
    total: int = 0


def overview() -> TaskStats:
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=6)).isoformat()
    sql = """
        SELECT
            SUM(status = 'todo') AS todo,
            SUM(status = 'doing') AS doing,
            SUM(status = 'done') AS done,
            SUM(status != 'done' AND due_date IS NOT NULL AND due_date != ''
                AND due_date < :today) AS overdue,
            SUM(status != 'done' AND due_date = :today) AS due_today,
            SUM(status = 'done' AND date(completed_at) >= :week_ago) AS completed_week,
            COUNT(*) AS total
        FROM tasks
    """
    with closing(get_connection()) as conn:
        row = conn.execute(sql, {"today": today, "week_ago": week_ago}).fetchone()
    return TaskStats(*(int(row[k] or 0) for k in
                       ("todo", "doing", "done", "overdue", "due_today",
                        "completed_week", "total")))


def focus_tasks(limit: int = 6) -> list[Task]:
    """今日聚焦：逾期 → 今天到期 → 高优先级进行中/待办。"""
    today = date.today().isoformat()
    sql = f"""
        SELECT {_COLS} FROM tasks
        WHERE status != 'done'
          AND (due_date <= :today OR priority = 'high')
        ORDER BY CASE WHEN due_date IS NOT NULL AND due_date != '' AND due_date < :today
                      THEN 0 ELSE 1 END,
                 due_date ASC,
                 CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                 id DESC
        LIMIT :limit
    """
    with closing(get_connection()) as conn:
        rows = conn.execute(sql, {"today": today, "limit": limit}).fetchall()
    return [Task.from_row(r) for r in rows]


def recent_completed(limit: int = 3) -> list[Task]:
    """最近完成的任务，用于工作台底部的时间线。"""
    sql = f"""
        SELECT {_COLS} FROM tasks
        WHERE status = 'done' AND completed_at IS NOT NULL AND completed_at != ''
        ORDER BY completed_at DESC, id DESC LIMIT :limit
    """
    with closing(get_connection()) as conn:
        return [Task.from_row(r) for r in conn.execute(sql, {"limit": limit}).fetchall()]


def completion_trend(days: int = 7) -> list[tuple[date, int]]:
    """最近 N 天每日完成数（含 0），按时间正序。"""
    start = date.today() - timedelta(days=days - 1)
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT date(completed_at) AS d, COUNT(*) AS n FROM tasks "
            "WHERE status = 'done' AND date(completed_at) >= ? GROUP BY d",
            (start.isoformat(),)).fetchall()
    counts = {r["d"]: r["n"] for r in rows}
    return [(start + timedelta(days=i), counts.get((start + timedelta(days=i)).isoformat(), 0))
            for i in range(days)]
