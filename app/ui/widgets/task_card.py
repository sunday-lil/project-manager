"""看板任务卡片控件。"""
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from app.constants import PRIORITY_COLORS, PRIORITY_LABELS, STATUS_LABELS, TaskStatus
from app.models.task import Task


class TaskCardWidget(QFrame):
    """单张看板卡片：标题、优先级色点、标签、截止日期、issue 编号、左右移动。"""

    move_requested = Signal(int, str)  # task_id, new_status
    edited = Signal(int)
    deleted = Signal(int)

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("taskCard")
        self.setStyleSheet(
            "#taskCard { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 6px; }"
            "#taskCard:hover { border-color: #4a90d9; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        # 标题行：优先级色点 + 标题
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {PRIORITY_COLORS[task.priority]}; font-size: 10px;")
        title_row.addWidget(dot)
        title = QLabel(task.title)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: bold; font-size: 13px; border: none;")
        title_row.addWidget(title, stretch=1)
        root.addLayout(title_row)

        # 元信息行：标签 / 截止日期 / issue 编号
        meta = QLabel(self._meta_text())
        meta.setWordWrap(True)
        meta.setStyleSheet("color: #666; font-size: 11px; border: none;")
        meta.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(meta)

        # 操作行：左右移动按钮（按当前状态决定可用方向）
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        order = [TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE]
        idx = order.index(task.status)
        if idx > 0:
            left = QToolButton(text="◀ " + STATUS_LABELS[order[idx - 1]])
            left.setToolTip("移到「" + STATUS_LABELS[order[idx - 1]] + "」")
            left.clicked.connect(
                lambda: self.move_requested.emit(task.id, order[idx - 1]))
            btn_row.addWidget(left)
        if idx < len(order) - 1:
            right = QToolButton(text=STATUS_LABELS[order[idx + 1]] + " ▶")
            right.setToolTip("移到「" + STATUS_LABELS[order[idx + 1]] + "」")
            right.clicked.connect(
                lambda: self.move_requested.emit(task.id, order[idx + 1]))
            btn_row.addWidget(right)
        root.addLayout(btn_row)

    def _meta_text(self) -> str:
        parts = [f"优先级：{PRIORITY_LABELS[self.task.priority]}"]
        if self.task.tags.strip():
            parts.append(" ".join(f"[{t.strip()}]" for t in self.task.tags.split(",") if t.strip()))
        if self.task.due_date:
            overdue = self.task.due_date < date.today().isoformat() and self.task.status != TaskStatus.DONE
            text = f"截止 {self.task.due_date}"
            parts.append(f'<span style="color:#e74c3c;">{text}（已过期）</span>' if overdue else text)
        if self.task.issue_number:
            parts.append(f'<span style="color:#1d6fb8;">#{self.task.issue_number}</span>')
        return " · ".join(parts)
