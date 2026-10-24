"""后台线程、CSV 导出与主窗口冒烟测试。"""
import time

from PySide6.QtCore import QEventLoop, QTimer

from app.core.workers import active_workers, run_async
from app.models.task import Task
from app.services import export_service


def test_run_async_delivers_result(qapp):
    got = []
    loop = QEventLoop()

    def done(value):
        got.append(value)
        loop.quit()

    run_async(lambda: 21 * 2, on_ok=done)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    assert got == [42]

    # 回调后 worker 引用会被释放（不要求立即为 0，给事件循环一轮机会）
    for _ in range(20):
        qapp.processEvents()
        time.sleep(0.01)
    assert active_workers() == 0


def test_run_async_error_is_friendly(qapp):
    got = []
    loop = QEventLoop()
    run_async(lambda: 1 / 0,
              on_err=lambda msg: (got.append(msg), loop.quit()))
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    assert got and "division by zero" in got[0]


def test_export_csv(isolated_db, tmp_path):
    from app.services import task_service
    task_service.create_task(Task(id=None, title="导出我", description="正文",
                                  status="done", tags="a,b"))
    target = tmp_path / "任务.csv"
    assert export_service.export_tasks_csv(target) == 1
    text = target.read_text(encoding="utf-8-sig")
    assert "导出我" in text and "已完成" in text


def test_main_window_smoke(isolated_db, qapp, monkeypatch):
    from app.core.settings import SettingsStore
    from app.services import task_service
    from app.ui import theme
    from app.ui.main_window import MainWindow

    SettingsStore.set("sync_workspace", "0")
    monkeypatch.setattr("app.ui.main_window.workspace_service.sync_workspace",
                        lambda repos: None)
    theme.apply(qapp, "light")

    window = MainWindow()
    try:
        assert window.stack.count() == 4
        assert window.nav_buttons["dashboard"].isChecked()

        window.kanban_tab.quick_edit.setText("冒烟任务")
        window.kanban_tab._quick_add()
        assert [t.title for t in task_service.list_tasks()] == ["冒烟任务"]

        for key in ("kanban", "repos", "github", "dashboard"):
            window._navigate(key)
            qapp.processEvents()
        assert window.nav_buttons["dashboard"].isChecked()

        window._apply_theme("dark", notify=False)
        qapp.processEvents()
        assert theme.mode() == "dark"
        window._apply_theme("light", notify=False)
        qapp.processEvents()
        assert theme.mode() == "light"
    finally:
        window.close()
