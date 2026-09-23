"""新建 Issue 对话框。"""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QVBoxLayout)


class IssueCreateDialog(QDialog):
    def __init__(self, owner_repo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"新建 Issue - {owner_repo}")
        self.setMinimumWidth(440)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("必填")
        form.addRow("标题：", self.title_edit)
        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText("正文（可选）")
        self.body_edit.setFixedHeight(120)
        form.addRow("正文：", self.body_edit)
        self.labels_edit = QLineEdit()
        self.labels_edit.setPlaceholderText("逗号分隔，如：bug,enhancement（可选）")
        form.addRow("标签：", self.labels_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self.title_edit.text().strip():
            self.title_edit.setPlaceholderText("标题不能为空")
            self.title_edit.setFocus()
            return
        self.accept()

    def values(self) -> tuple[str, str, list[str]]:
        labels = [t.strip() for t in self.labels_edit.text().split(",") if t.strip()]
        return self.title_edit.text().strip(), self.body_edit.toPlainText().strip(), labels
