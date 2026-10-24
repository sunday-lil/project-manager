"""看板任务卡片控件。"""
from datetime import date

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from app.constants import PRIORITY_LABELS, STATUS_LABELS, TaskStatus
from app.models.task import Task


class TaskCardWidget(QFrame):
    """单张看板卡片：标题、优先级、标签、截止日期、Issue 链接、移动箭头。"""

    move_requested = Signal(int, str)      # task_id, new_status
    edit_requested = Signal(int)
    menu_requested = Signal(int, QPoint)   # task_id, 全局坐标

    def __init__(self, task: Task, repo_name: str = "", parent=None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("taskCard")
        self.setProperty("prio", task.priority)
        self.setToolTip(task.description or task.title)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        title = QLabel(task.title)
        title.setObjectName("cardTitle")
        title.setProperty("done", task.status == TaskStatus.DONE)
        title.setWordWrap(True)
        title.setMaximumHeight(40)
        title.setStyleSheet("font-weight: 600; font-size: 13px; background: transparent;")
        root.addWidget(title)

        meta = QHBoxLayout()
        meta.setSpacing(5)
        prio = QLabel(PRIORITY_LABELS.get(task.priority, task.priority))
        prio.setProperty("role", "chip")
        prio.setProperty("tone", {"high": "danger", "medium": "warning"}.get(task.priority, "success"))
        prio.setToolTip(f"优先级：{PRIORITY_LABELS.get(task.priority, task.priority)}")
        meta.addWidget(prio)

        if task.due_date:
            due = QLabel(self._due_text(task))
            due.setProperty("role", "chip")
            due.setProperty("tone", self._due_tone(task))
            meta.addWidget(due)
        if task.issue_number:
            issue = QLabel(f'<a href="{task.issue_url or ""}" style="color:{self._accent()};'
                           f' text-decoration:none;">#{task.issue_number}</a>')
            issue.setOpenExternalLinks(True)
            issue.setProperty("role", "chip")
            issue.setProperty("tone", "accent")
            meta.addWidget(issue)
        if repo_name:
            repo = QLabel(repo_name)
            repo.setProperty("role", "faint")
            meta.addWidget(repo)
        meta.addStretch(1)

        order = list(TaskStatus.ALL)
        idx = order.index(task.status) if task.status in order else 0
        if idx > 0:
            left = QToolButton(text="←")
            left.setToolTip(f"移到「{STATUS_LABELS[order[idx - 1]]}」")
            left.clicked.connect(lambda: self.move_requested.emit(task.id, order[idx - 1]))
            meta.addWidget(left)
        if idx < len(order) - 1:
            right = QToolButton(text="→")
            right.setToolTip(f"移到「{STATUS_LABELS[order[idx + 1]]}」")
            right.clicked.connect(lambda: self.move_requested.emit(task.id, order[idx + 1]))
            meta.addWidget(right)
        root.addLayout(meta)

        if task.tag_list:
            tags = QHBoxLayout()
            tags.setSpacing(4)
            for tag in task.tag_list[:3]:
                chip = QLabel(tag)
                chip.setProperty("role", "chip")
                tags.addWidget(chip)
            if len(task.tag_list) > 3:
                more = QLabel(f"+{len(task.tag_list) - 3}")
                more.setProperty("role", "faint")
                tags.addWidget(more)
            tags.addStretch(1)
            root.addLayout(tags)

    @staticmethod
    def _accent() -> str:
        from app.ui import theme
        return theme.tone("accent")

    @staticmethod
    def _due_text(task: Task) -> str:
        try:
            y, m, d = map(int, task.due_date.split("-"))
            due = date(y, m, d)
        except (ValueError, AttributeError):
            return task.due_date
        delta = (due - date.today()).days
        if task.status == TaskStatus.DONE:
            return f"{due.month}/{due.day}"
        if delta < 0:
            return f"逾期 {-delta} 天"
        if delta == 0:
            return "今天"
        if delta == 1:
            return "明天"
        return f"{due.month}/{due.day}"

    @staticmethod
    def _due_tone(task: Task) -> str:
        if not task.due_date or task.status == TaskStatus.DONE:
            return ""
        today = date.today()
        if task.due_date < today.isoformat():
            return "danger"
        if task.due_date == today.isoformat():
            return "warning"
        return ""

    # ---------- 交互 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self.menu_requested.emit(self.task.id, self.mapToGlobal(event.position().toPoint()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self.task.id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
