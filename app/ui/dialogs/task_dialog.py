"""新建/编辑任务表单。"""
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout)

from app.constants import PRIORITY_LABELS, STATUS_LABELS, Priority, TaskStatus
from app.models.task import Task

_EMPTY_DATE = QDate(2000, 1, 1)  # QDateEdit 最小值代表"无截止日期"


class TaskDialog(QDialog):
    def __init__(self, repos: list, task: Task | None = None, parent=None):
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("编辑任务" if task else "新建任务")
        self.setMinimumWidth(420)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("必填")
        form.addRow("标题：", self.title_edit)

        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("任务描述（推送为 Issue 时作为正文）")
        self.desc_edit.setFixedHeight(80)
        form.addRow("描述：", self.desc_edit)

        self.status_box = QComboBox()
        for s in TaskStatus.ALL:
            self.status_box.addItem(STATUS_LABELS[s], s)
        form.addRow("状态：", self.status_box)

        self.priority_box = QComboBox()
        for p in Priority.ALL:
            self.priority_box.addItem(PRIORITY_LABELS[p], p)
        form.addRow("优先级：", self.priority_box)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMinimumDate(_EMPTY_DATE)
        self.date_edit.setDate(_EMPTY_DATE)
        self.date_edit.setSpecialValueText("无")
        form.addRow("截止日期：", self.date_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("逗号分隔，如：bug,前端")
        form.addRow("标签：", self.tags_edit)

        self.repo_box = QComboBox()
        self.repo_box.addItem("（不关联）", None)
        for r in repos:
            self.repo_box.addItem(r.name or r.path, r.id)
        form.addRow("关联仓库：", self.repo_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if task:
            self._fill_form()

    def _fill_form(self) -> None:
        t = self.task
        self.title_edit.setText(t.title)
        self.desc_edit.setPlainText(t.description)
        self.status_box.setCurrentIndex(TaskStatus.ALL.index(t.status))
        self.priority_box.setCurrentIndex(Priority.ALL.index(t.priority))
        if t.due_date:
            y, m, d = map(int, t.due_date.split("-"))
            self.date_edit.setDate(QDate(y, m, d))
        self.tags_edit.setText(t.tags)
        idx = self.repo_box.findData(t.repo_id)
        self.repo_box.setCurrentIndex(idx if idx >= 0 else 0)

    def _validate(self) -> None:
        if not self.title_edit.text().strip():
            self.title_edit.setPlaceholderText("标题不能为空")
            self.title_edit.setFocus()
            return
        self.accept()

    def result_task(self) -> Task:
        """从表单构造 Task（新建时 id=None）。"""
        due = None
        if self.date_edit.date() != _EMPTY_DATE:
            due = self.date_edit.date().toString("yyyy-MM-dd")
        t = self.task or Task(id=None, title="")
        t.title = self.title_edit.text().strip()
        t.description = self.desc_edit.toPlainText().strip()
        t.status = self.status_box.currentData()
        t.priority = self.priority_box.currentData()
        t.due_date = due
        t.tags = self.tags_edit.text().strip()
        t.repo_id = self.repo_box.currentData()
        return t
