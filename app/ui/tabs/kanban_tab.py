"""任务看板 Tab：三列看板 + 工具栏 + GitHub 同步。"""
from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGroupBox, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from app.constants import STATUS_LABELS, TaskStatus
from app.core.workers import run_async
from app.models.task import Task
from app.services import repo_service, sync_service, task_service
from app.ui.dialogs.task_dialog import TaskDialog
from app.ui.widgets.task_card import TaskCardWidget

MIME_TASK = "application/x-pm-task"


class TaskListWidget(QListWidget):
    """支持跨列拖拽的任务列表（同列内不排序，列由状态决定）。"""

    task_dropped = Signal()

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.status = status
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def startDrag(self, actions):
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(MIME_TASK, str(item.data(Qt.ItemDataRole.UserRole)).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.source() is not None and event.mimeData().hasFormat(MIME_TASK):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is not None and event.source() is not self and event.mimeData().hasFormat(MIME_TASK):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.source() is self:
            event.ignore()  # 同列放下无意义（不做排序）
            return
        task_id = int(bytes(event.mimeData().data(MIME_TASK)).decode("utf-8"))
        task_service.move_task(task_id, self.status)
        event.acceptProposedAction()
        self.task_dropped.emit()


class KanbanTab(QWidget):
    status_message = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._tasks_by_id: dict[int, Task] = {}

        # 工具栏
        new_btn = QPushButton("＋ 新建任务")
        new_btn.clicked.connect(self._new_task)
        self.repo_filter = QComboBox()
        self.repo_filter.setMinimumWidth(180)
        self.repo_filter.currentIndexChanged.connect(lambda _: self.reload())
        pull_btn = QPushButton("⬇ 拉取 Issues")
        pull_btn.setToolTip("把选中仓库的 open Issues 拉取为待办任务")
        pull_btn.clicked.connect(self._pull_issues)

        toolbar = QHBoxLayout()
        toolbar.addWidget(new_btn)
        toolbar.addWidget(QLabel("仓库过滤："))
        toolbar.addWidget(self.repo_filter, stretch=1)
        toolbar.addWidget(pull_btn)
        toolbar.addStretch(1)

        # 三列看板
        columns = QHBoxLayout()
        self.lists: dict[str, TaskListWidget] = {}
        for status in TaskStatus.ALL:
            lst = TaskListWidget(status)
            lst.setSpacing(4)
            lst.task_dropped.connect(self.reload)
            lst.customContextMenuRequested.connect(lambda pos, l=lst: self._menu(l, pos))
            box = QGroupBox(STATUS_LABELS[status])
            v = QVBoxLayout(box)
            v.setContentsMargins(4, 4, 4, 4)
            v.addWidget(lst)
            columns.addWidget(box, stretch=1)
            self.lists[status] = lst

        root = QVBoxLayout(self)
        root.addLayout(toolbar)
        root.addLayout(columns, stretch=1)

    # ---------- 数据加载 ----------

    def reload(self) -> None:
        repo_id = self.repo_filter.currentData()
        tasks = task_service.list_tasks(repo_id=repo_id)
        self._tasks_by_id = {t.id: t for t in tasks}
        for status, lst in self.lists.items():
            lst.clear()
            for t in tasks:
                if t.status == status:
                    card = TaskCardWidget(t)
                    card.move_requested.connect(self._move)
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, t.id)
                    item.setSizeHint(card.sizeHint())
                    lst.addItem(item)
                    lst.setItemWidget(item, card)

    def refresh_repos(self) -> None:
        """重填仓库过滤下拉（保留当前选择）。"""
        repos = repo_service.list_repos()
        selected = self.repo_filter.currentData()
        self.repo_filter.blockSignals(True)
        self.repo_filter.clear()
        self.repo_filter.addItem("全部仓库", None)
        for r in repos:
            self.repo_filter.addItem(r.name or r.path, r.id)
        if selected is not None:
            idx = self.repo_filter.findData(selected)
            self.repo_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.repo_filter.blockSignals(False)
        self.reload()

    # ---------- 任务操作 ----------

    def _current_repo_id(self):
        return self.repo_filter.currentData()

    def _task_of(self, lst: TaskListWidget):
        item = lst.currentItem()
        return self._tasks_by_id.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _new_task(self) -> None:
        repos = repo_service.list_repos()
        dlg = TaskDialog(repos, parent=self)
        if dlg.exec() == TaskDialog.DialogCode.Accepted:
            task_service.create_task(dlg.result_task())
            self.reload()
            self.status_message.emit("任务已创建")

    def _move(self, task_id: int, new_status: str) -> None:
        task_service.move_task(task_id, new_status)
        self.reload()

    def _menu(self, lst: TaskListWidget, pos) -> None:
        task = self._task_of(lst)
        if task is None:
            return
        menu = QMenu(self)
        for status in TaskStatus.ALL:
            if status != task.status:
                act = menu.addAction(f"移到「{STATUS_LABELS[status]}」")
                act.triggered.connect(lambda _, s=status: self._move(task.id, s))
        menu.addSeparator()
        edit = menu.addAction("编辑")
        edit.triggered.connect(lambda: self._edit(task.id))
        push = menu.addAction("推送为 GitHub Issue" + (f"（已关联 #{task.issue_number}）" if task.issue_number else ""))
        push.triggered.connect(lambda: self._push(task.id))
        menu.addSeparator()
        delete = menu.addAction("删除")
        delete.triggered.connect(lambda: self._delete(task.id))
        menu.exec(lst.viewport().mapToGlobal(pos))

    def _edit(self, task_id: int) -> None:
        task = task_service.get_task(task_id)
        if task is None:
            return
        dlg = TaskDialog(repo_service.list_repos(), task, parent=self)
        if dlg.exec() == TaskDialog.DialogCode.Accepted:
            task_service.update_task(dlg.result_task())
            self.reload()
            self.status_message.emit("任务已更新")

    def _delete(self, task_id: int) -> None:
        task = self._tasks_by_id.get(task_id)
        if task is None:
            return
        if QMessageBox.question(self, "删除任务", f"确定删除「{task.title}」吗？") == QMessageBox.StandardButton.Yes:
            task_service.delete_task(task_id)
            self.reload()
            self.status_message.emit("任务已删除")

    # ---------- GitHub 同步 ----------

    def _pull_issues(self) -> None:
        repo_id = self._current_repo_id()
        if repo_id is None:
            QMessageBox.information(self, "拉取 Issues", "请先在仓库过滤中选择具体仓库")
            return
        repo = repo_service.get_repo(repo_id)
        if repo is None:
            QMessageBox.warning(self, "拉取 Issues", "关联仓库不存在，请重新扫描")
            return
        if not self.ctx.has_token():
            QMessageBox.warning(self, "需要 Token", "请先在「设置」中配置 GitHub Token")
            return
        gh = self.ctx.service()
        self.status_message.emit(f"正在拉取 {repo.name} 的 Issues…")
        run_async(lambda: sync_service.pull_issues(gh, repo_id),
                  on_ok=lambda msg: (self.reload(), self.status_message.emit(msg)),
                  on_err=lambda e: self.status_message.emit(f"拉取失败：{e}"))

    def _push(self, task_id: int) -> None:
        task = task_service.get_task(task_id)
        if task is None:
            return
        if task.issue_number:
            QMessageBox.information(self, "推送任务", f"任务已关联 Issue #{task.issue_number}，请勿重复推送")
            return
        if not self.ctx.has_token():
            QMessageBox.warning(self, "需要 Token", "请先在「设置」中配置 GitHub Token")
            return
        gh = self.ctx.service()
        self.status_message.emit("正在创建 Issue…")
        run_async(lambda: sync_service.push_task(gh, task_id),
                  on_ok=lambda msg: (self.reload(), self.status_message.emit(msg)),
                  on_err=lambda e: self.status_message.emit(f"推送失败：{e}"))
