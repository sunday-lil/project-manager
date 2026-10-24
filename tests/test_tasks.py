"""任务 CRUD、完成时间维护与筛选。"""
from datetime import date, timedelta

from app.models.task import Task
from app.services import stats_service, task_service


def make(title, **kw) -> int:
    return task_service.create_task(Task(id=None, title=title, **kw))


def test_completed_at_lifecycle(isolated_db):
    tid = make("搬家")
    assert task_service.get_task(tid).completed_at is None

    task_service.move_task(tid, "done")
    done = task_service.get_task(tid)
    assert done.completed_at and done.status == "done"

    task_service.move_task(tid, "doing")
    assert task_service.get_task(tid).completed_at is None

    task_service.move_task(tid, "done")
    assert task_service.get_task(tid).completed_at is not None


def test_update_task_status_keeps_completed_at(isolated_db):
    tid = make("写周报", status="done")
    task = task_service.get_task(tid)
    assert task.completed_at

    task.title = "写月报"
    task_service.update_task(task)
    assert task_service.get_task(tid).completed_at

    task.status = "todo"
    task_service.update_task(task)
    assert task_service.get_task(tid).completed_at is None


def test_filters(isolated_db):
    make("修复登录 bug", priority="high", tags="bug,前端",
         due_date=(date.today() - timedelta(days=1)).isoformat(), repo_id=None)
    make("写文档", priority="low", tags="docs",
         due_date=date.today().isoformat())
    make("无截止日", priority="medium", tags="杂项")
    make("已完成 bug", priority="high", tags="bug", status="done")

    assert {t.title for t in task_service.list_tasks(search="bug")} == {"修复登录 bug", "已完成 bug"}
    assert [t.title for t in task_service.list_tasks(priority="low")] == ["写文档"]
    assert {t.title for t in task_service.list_tasks(tag="bug")} == {"修复登录 bug", "已完成 bug"}
    assert [t.title for t in task_service.list_tasks(due="today")] == ["写文档"]
    assert [t.title for t in task_service.list_tasks(due="overdue")] == ["修复登录 bug"]
    assert {t.title for t in task_service.list_tasks(due="none")} == {"无截止日", "已完成 bug"}
    assert "docs" in task_service.all_tags()


def test_priority_order(isolated_db):
    make("低", priority="low")
    make("高", priority="high")
    make("中", priority="medium")
    titles = [t.title for t in task_service.list_tasks()]
    assert titles == ["高", "中", "低"]


def test_issue_link_and_dedup_helpers(isolated_db):
    tid = make("关联", repo_id=None)
    task_service.link_issue(tid, 42, "https://github.com/acme/x/issues/42")
    task = task_service.get_task(tid)
    assert task.issue_number == 42 and task.synced_at


def test_stats_overview_focus_trend(isolated_db):
    today = date.today()
    make("逾期", priority="high", due_date=(today - timedelta(days=2)).isoformat())
    make("今天", priority="medium", due_date=today.isoformat())
    make("进行", priority="high", status="doing")
    tid = make("完成", status="done")
    task_service.link_issue(tid, 1, "x")

    stats = stats_service.overview()
    assert (stats.todo, stats.doing, stats.done, stats.total) == (2, 1, 1, 4)
    assert stats.overdue == 1
    assert stats.due_today == 1
    assert stats.completed_week == 1

    focus = stats_service.focus_tasks(5)
    assert focus[0].title == "逾期"
    assert {t.title for t in focus} >= {"逾期", "今天", "进行"}

    trend = stats_service.completion_trend(7)
    assert len(trend) == 7
    assert sum(n for _, n in trend) == 1
    assert trend[-1][0] == date.today()
