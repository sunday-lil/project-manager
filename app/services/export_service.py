"""任务导出（CSV，UTF-8 BOM 方便 Excel 直接打开）。"""
import csv
from pathlib import Path

from app.constants import PRIORITY_LABELS, STATUS_LABELS
from app.services import repo_service, task_service


def export_tasks_csv(target: str | Path) -> int:
    """导出全部任务，返回条数。"""
    tasks = task_service.list_tasks()
    repos = {r.id: r for r in repo_service.list_repos()}
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "标题", "描述", "状态", "优先级", "截止日期", "标签",
                         "关联仓库", "Issue", "完成时间", "创建时间", "更新时间"])
        for t in tasks:
            repo = repos.get(t.repo_id) if t.repo_id else None
            writer.writerow([
                t.id, t.title, t.description,
                STATUS_LABELS.get(t.status, t.status),
                PRIORITY_LABELS.get(t.priority, t.priority),
                t.due_date or "", t.tags,
                repo.name if repo else "",
                f"#{t.issue_number}" if t.issue_number else "",
                t.completed_at or "", t.created_at or "", t.updated_at or "",
            ])
    return len(tasks)
