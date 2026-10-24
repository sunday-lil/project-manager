"""任务看板：三列拖拽 + 搜索筛选 + 快速添加 + GitHub 同步。"""
from PySide6.QtCore import QMimeData, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    PRIORITY_LABELS,
    STATUS_HINTS,
    STATUS_LABELS,
    DueFilter,
    Priority,
    TaskStatus,
)
from app.core.workers import run_async
from app.models.task import Task
from app.services import repo_service, sync_service, task_service
from app.ui import theme
from app.ui.dialogs.task_dialog import TaskDialog
from app.ui.widgets.common import PageHeader
from app.ui.widgets.task_card import TaskCardWidget

MIME_TASK = "application/x-pm-task"


class TaskListWidget(QListWidget):
    """支持跨列拖拽的任务列表；空列自绘占位提示。"""

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
        self.setSpacing(6)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._relayout_pending = False

    def schedule_relayout(self) -> None:
        """卡片宽度确定后重算每项高度，避免标题换行导致的大片留白。"""
        if self._relayout_pending:
            return
        self._relayout_pending = True
        QTimer.singleShot(0, self._relayout_items)

    def _relayout_items(self) -> None:
        self._relayout_pending = False
        width = self.viewport().width() - 8
        if width < 80:
            return
        for i in range(self.count()):
            item = self.item(i)
            card = self.itemWidget(item)
            if card is None:
                continue
            card.setFixedWidth(width)
            layout = card.layout()
            if layout is not None:
                layout.activate()
            item.setSizeHint(QSize(width, card.sizeHint().height()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.schedule_relayout()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.count():
            return
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)
        p.setPen(QColor(theme.tone("faint")))
        rect = self.viewport().rect().adjusted(8, 34, -8, 0)
        p.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   "暂无任务\n拖拽卡片到这里")
        p.end()

    def startDrag(self, actions) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(MIME_TASK, str(item.data(Qt.ItemDataRole.UserRole)).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        widget = self.itemWidget(item)
        if widget is not None:
            pix = widget.grab()
            drag.setPixmap(pix)
            drag.setHotSpot(QPoint(pix.width() // 2, 18))
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.source() is not None and event.mimeData().hasFormat(MIME_TASK):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if (event.source() is not None and event.source() is not self
                and event.mimeData().hasFormat(MIME_TASK)):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.source() is self:
            event.ignore()
            return
        try:
            task_id = int(bytes(event.mimeData().data(MIME_TASK)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return
        task_service.move_task(task_id, self.status)
        event.acceptProposedAction()
        self.task_dropped.emit()


class BoardColumn(QFrame):
    """一列：标题 + 计数 + 小加号 + 列表。"""

    add_requested = Signal(str)

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.status = status
        self.setProperty("role", "column")

        title = QLabel(STATUS_LABELS[status])
        title.setProperty("role", "h2")
        hint = QLabel(STATUS_HINTS[status])
        hint.setProperty("role", "faint")
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(title)
        text.addWidget(hint)

        self.count = QLabel("0")
        self.count.setProperty("role", "chip")
        self.count.setProperty("tone", {"todo": "accent", "doing": "warning",
                                        "done": "success"}[status])

        add = QToolButton(text="＋")
        add.setToolTip(f"新建「{STATUS_LABELS[status]}」任务")
        add.clicked.connect(lambda: self.add_requested.emit(self.status))

        head = QHBoxLayout()
        head.setSpacing(6)
        head.addLayout(text)
        head.addStretch(1)
        head.addWidget(self.count)
        head.addWidget(add)

        self.list = TaskListWidget(status)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)
        layout.addLayout(head)
        layout.addWidget(self.list, stretch=1)

    def set_count(self, value: int) -> None:
        self.count.setText(str(value))


class KanbanTab(QWidget):
    status_message = Signal(str)
    tasks_changed = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self._tasks_by_id: dict[int, Task] = {}
        self._repo_names: dict[int, str] = {}
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.reload)

        self.header = PageHeader("任务看板", "")
        self.pull_btn = QPushButton("拉取 Issues")
        self.pull_btn.setToolTip("把当前仓库的 open Issues 拉取为待办任务")
        self.pull_btn.clicked.connect(self._pull_issues)
        self.header.add_action(self.pull_btn)
        new_btn = QPushButton("＋ 新建任务")
        new_btn.setProperty("variant", "primary")
        new_btn.clicked.connect(lambda: self.new_task())
        self.header.add_action(new_btn)

        # 筛选行
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索标题、描述、标签…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(210)
        self.search_edit.textChanged.connect(lambda _: self._search_timer.start())

        self.repo_filter = QComboBox()
        self.repo_filter.setMinimumWidth(140)
        self.repo_filter.currentIndexChanged.connect(lambda _: self.reload())

        self.priority_filter = QComboBox()
        self.priority_filter.addItem("全部优先级", None)
        for p in Priority.ALL:
            self.priority_filter.addItem(f"{PRIORITY_LABELS[p]}优先级", p)
        self.priority_filter.currentIndexChanged.connect(lambda _: self.reload())

        self.due_filter = QComboBox()
        for key in (DueFilter.ALL, DueFilter.TODAY, DueFilter.OVERDUE,
                    DueFilter.WEEK, DueFilter.NONE):
            self.due_filter.addItem(DueFilter.LABELS[key], key)
        self.due_filter.currentIndexChanged.connect(lambda _: self.reload())

        self.tag_filter = QComboBox()
        self.tag_filter.setMinimumWidth(110)
        self.tag_filter.addItem("全部标签", None)
        self.tag_filter.currentIndexChanged.connect(lambda _: self.reload())

        reset = QPushButton("重置")
        reset.setProperty("variant", "ghost")
        reset.clicked.connect(self.reset_filters)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self.search_edit, stretch=1)
        filters.addWidget(self.repo_filter)
        filters.addWidget(self.priority_filter)
        filters.addWidget(self.due_filter)
        filters.addWidget(self.tag_filter)
        filters.addWidget(reset)

        # 快速添加
        self.quick_edit = QLineEdit()
        self.quick_edit.setPlaceholderText("快速添加任务，回车即建（默认进入待办、中优先级）")
        self.quick_edit.returnPressed.connect(self._quick_add)
        quick_btn = QPushButton("添加")
        quick_btn.clicked.connect(self._quick_add)
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        quick_row.addWidget(self.quick_edit, stretch=1)
        quick_row.addWidget(quick_btn)

        # 三列
        self.columns: dict[str, BoardColumn] = {}
        columns = QHBoxLayout()
        columns.setSpacing(12)
        for status in TaskStatus.ALL:
            col = BoardColumn(status)
            col.add_requested.connect(lambda s: self.new_task(status=s))
            col.list.task_dropped.connect(self._on_dropped)
            columns.addWidget(col, stretch=1)
            self.columns[status] = col

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)
        root.addWidget(self.header)
        root.addLayout(filters)
        root.addLayout(quick_row)
        root.addLayout(columns, stretch=1)

    # ---------- 数据加载 ----------

    def reload(self) -> None:
        self._refresh_repo_filter()
        self._refresh_tag_filter()
        repo_id = self.repo_filter.currentData()
        tasks = task_service.list_tasks(
            repo_id=repo_id,
            search=self.search_edit.text(),
            priority=self.priority_filter.currentData(),
            tag=self.tag_filter.currentData(),
            due=self.due_filter.currentData() or DueFilter.ALL,
        )
        self._tasks_by_id = {t.id: t for t in tasks}
        self._repo_names = {r.id: r.name for r in repo_service.list_repos() if r.id}

        by_status: dict[str, list[Task]] = {s: [] for s in TaskStatus.ALL}
        for t in tasks:
            by_status.setdefault(t.status, []).append(t)

        for status, col in self.columns.items():
            col.list.clear()
            for task in by_status.get(status, []):
                card = TaskCardWidget(task, self._repo_names.get(task.repo_id, ""))
                card.move_requested.connect(self._move)
                card.edit_requested.connect(self.edit_task)
                card.menu_requested.connect(self._card_menu)
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                item.setSizeHint(card.sizeHint())
                col.list.addItem(item)
                col.list.setItemWidget(item, card)
            col.set_count(len(by_status.get(status, [])))
            col.list.schedule_relayout()

        overdue = sum(1 for t in tasks if t.is_overdue)
        bits = [f"{len(tasks)} 个任务"]
        if overdue:
            bits.append(f"{overdue} 个逾期")
        if self._filters_active():
            bits.append("已筛选")
        self.header.set_subtitle(" · ".join(bits) + "　·　拖拽卡片在状态间流转，双击编辑")

    def refresh_repos(self) -> None:
        self._refresh_repo_filter()
        self.reload()

    def _refresh_repo_filter(self) -> None:
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

    def _refresh_tag_filter(self) -> None:
        tags = task_service.all_tags()
        selected = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("全部标签", None)
        for tag in tags:
            self.tag_filter.addItem(tag, tag)
        if selected:
            idx = self.tag_filter.findData(selected)
            self.tag_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.tag_filter.blockSignals(False)

    def _filters_active(self) -> bool:
        return bool(self.search_edit.text().strip()
                    or self.repo_filter.currentData() is not None
                    or self.priority_filter.currentData() is not None
                    or self.due_filter.currentData() != DueFilter.ALL
                    or self.tag_filter.currentData() is not None)

    def reset_filters(self) -> None:
        for combo in (self.repo_filter, self.priority_filter, self.due_filter, self.tag_filter):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.search_edit.clear()
        self.reload()

    # ---------- 任务操作 ----------

    def new_task(self, status: str = TaskStatus.TODO) -> None:
        dlg = TaskDialog(repo_service.list_repos(), parent=self,
                         default_repo_id=self.repo_filter.currentData(),
                         default_status=status)
        if dlg.exec() == TaskDialog.DialogCode.Accepted:
            task_service.create_task(dlg.result_task())
            self._after_change("任务已创建")

    def edit_task(self, task_id: int) -> None:
        task = task_service.get_task(task_id)
        if task is None:
            return
        dlg = TaskDialog(repo_service.list_repos(), task, parent=self)
        if dlg.exec() == TaskDialog.DialogCode.Accepted:
            task_service.update_task(dlg.result_task())
            self._after_change("任务已更新")

    def _quick_add(self) -> None:
        title = self.quick_edit.text().strip()
        if not title:
            self.quick_edit.setFocus()
            return
        task_service.create_task(Task(
            id=None, title=title, status=TaskStatus.TODO, priority=Priority.MEDIUM,
            repo_id=self.repo_filter.currentData()))
        self.quick_edit.clear()
        self._after_change("已添加：" + (title[:24] + ("…" if len(title) > 24 else "")))

    def _move(self, task_id: int, new_status: str) -> None:
        task_service.move_task(task_id, new_status)
        self._after_change(None)

    def _on_dropped(self) -> None:
        self._after_change(None)

    def _after_change(self, message: str | None) -> None:
        self.reload()
        self.tasks_changed.emit()
        if message:
            self.status_message.emit(message)

    def _delete(self, task_id: int) -> None:
        task = self._tasks_by_id.get(task_id) or task_service.get_task(task_id)
        if task is None:
            return
        if QMessageBox.question(self, "删除任务", f"确定删除「{task.title}」吗？") \
                == QMessageBox.StandardButton.Yes:
            task_service.delete_task(task_id)
            self._after_change("任务已删除")

    def _card_menu(self, task_id: int, pos: QPoint) -> None:
        task = self._tasks_by_id.get(task_id) or task_service.get_task(task_id)
        if task is None:
            return
        menu = QMenu(self)
        for status in TaskStatus.ALL:
            if status != task.status:
                act = menu.addAction(f"移到「{STATUS_LABELS[status]}」")
                act.triggered.connect(lambda _, s=status: self._move(task_id, s))
        menu.addSeparator()
        edit = menu.addAction("编辑…")
        edit.triggered.connect(lambda: self.edit_task(task_id))
        push = menu.addAction("推送为 GitHub Issue"
                              + (f"（已关联 #{task.issue_number}）" if task.issue_number else ""))
        push.triggered.connect(lambda: self._push(task_id, task))
        menu.addSeparator()
        delete = menu.addAction("删除")
        delete.triggered.connect(lambda: self._delete(task_id))
        menu.exec(pos)

    def focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ---------- GitHub 同步 ----------

    def _pull_issues(self) -> None:
        repo_id = self.repo_filter.currentData()
        if repo_id is None:
            QMessageBox.information(self, "拉取 Issues", "请先在「仓库」筛选中选择具体仓库")
            return
        repo = repo_service.get_repo(repo_id)
        if repo is None:
            QMessageBox.warning(self, "拉取 Issues", "关联仓库不存在，请重新扫描")
            return
        if not self.ctx.has_token():
            QMessageBox.warning(self, "需要 Token", "请先在「设置」中配置 GitHub Token")
            return
        gh = self.ctx.service()
        self.pull_btn.setEnabled(False)
        self.status_message.emit(f"正在拉取 {repo.name} 的 Issues…")

        def done(msg):
            self.pull_btn.setEnabled(True)
            self.status_message.emit(msg)
            self._after_change(None)

        def failed(err):
            self.pull_btn.setEnabled(True)
            self.status_message.emit(f"拉取失败：{err}")

        run_async(lambda: sync_service.pull_issues(gh, repo_id), on_ok=done, on_err=failed)

    def _push(self, task_id: int, task: Task) -> None:
        if task.issue_number:
            QMessageBox.information(self, "推送任务",
                                    f"任务已关联 Issue #{task.issue_number}，请勿重复推送")
            return
        if not self.ctx.has_token():
            QMessageBox.warning(self, "需要 Token", "请先在「设置」中配置 GitHub Token")
            return
        gh = self.ctx.service()
        self.status_message.emit("正在创建 Issue…")
        run_async(lambda: sync_service.push_task(gh, task_id),
                  on_ok=lambda msg: (self.status_message.emit(msg), self._after_change(None)),
                  on_err=lambda e: self.status_message.emit(f"推送失败：{e}"))
