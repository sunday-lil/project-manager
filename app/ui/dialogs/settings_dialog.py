"""设置对话框：GitHub Token、扫描根目录（多行）、合并方式。"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from app.constants import MERGE_METHOD_LABELS, MERGE_METHODS, SETTING_MERGE_METHOD
from app.core.settings import SettingsStore, get_github_token, set_github_token


class SettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(480)

        form = QFormLayout()

        self.token_edit = QLineEdit(get_github_token() or "")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("ghp_... 或 github_pat_...")
        show_btn = QCheckBox("显示")
        show_btn.toggled.connect(
            lambda on: self.token_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        token_row = QHBoxLayout()
        token_row.addWidget(self.token_edit, stretch=1)
        token_row.addWidget(show_btn)
        form.addRow("GitHub Token：", token_row)
        tip = QLabel("建议使用 fine-grained token：仅勾选需要管理的仓库，权限选 Metadata(读)、Issues(读写)、"
                     "Pull requests(读写)、Contents(读写)。Token 仅以明文保存在本机。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", tip)

        self.root_edit = QPlainTextEdit("\n".join(SettingsStore.get_scan_roots()))
        self.root_edit.setPlaceholderText("每行一个扫描根目录，例如：\nC:\\Users\\dog51\\Desktop\nE:\\minecraft dev")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_root)
        root_row = QHBoxLayout()
        root_row.addWidget(self.root_edit, stretch=1)
        root_row.addWidget(browse)
        form.addRow("仓库扫描根目录：", root_row)
        root_tip = QLabel("每行一个目录，保存后自动重新扫描。")
        root_tip.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", root_tip)

        self.merge_box = QComboBox()
        for m in MERGE_METHODS:
            self.merge_box.addItem(MERGE_METHOD_LABELS[m], m)
        saved = SettingsStore.get(SETTING_MERGE_METHOD)
        if saved in MERGE_METHODS:
            self.merge_box.setCurrentIndex(MERGE_METHODS.index(saved))
        form.addRow("默认合并方式：", self.merge_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "添加扫描根目录", self._last_root() or "")
        if path and path not in self._roots():
            self.root_edit.appendPlainText(path)

    def _roots(self) -> list[str]:
        return [line.strip() for line in self.root_edit.toPlainText().splitlines() if line.strip()]

    def _last_root(self) -> str:
        roots = self._roots()
        return roots[-1] if roots else ""

    def _save(self) -> None:
        set_github_token(self.token_edit.text().strip())
        SettingsStore.set_scan_roots(self._roots())
        SettingsStore.set(SETTING_MERGE_METHOD, self.merge_box.currentData())
        self.settings_saved.emit()
        self.accept()
