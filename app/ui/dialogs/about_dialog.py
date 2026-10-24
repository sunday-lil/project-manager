"""关于对话框：版本、技术栈、数据位置。"""
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.constants import APP_NAME, APP_TAGLINE, APP_VERSION, DATA_DIR, LOG_PATH
from app.ui.brand import app_icon


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"关于 {APP_NAME}")
        self.setMinimumWidth(460)

        icon = QLabel()
        icon.setPixmap(app_icon(64).pixmap(64, 64))
        name = QLabel(APP_NAME)
        name.setProperty("role", "h1")
        version = QLabel(f"v{APP_VERSION} · {APP_TAGLINE}")
        version.setProperty("role", "faint")

        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(name)
        text.addWidget(version)
        head.addLayout(text)
        head.addStretch(1)

        desc = QLabel("本地任务看板 + git 仓库状态 + GitHub Issues/PR 的个人工作台。"
                      "数据只存在本机：SQLite 位于数据目录，Token 用 Windows DPAPI 加密。")
        desc.setWordWrap(True)
        desc.setProperty("role", "muted")

        data_btn = QPushButton("打开数据目录")
        data_btn.clicked.connect(lambda: os.startfile(DATA_DIR))
        log_btn = QPushButton("打开日志")
        log_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_PATH))))
        repo_btn = QPushButton("GitHub 项目")
        repo_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/sunday-lil/project-manager")))
        row = QHBoxLayout()
        row.addWidget(data_btn)
        row.addWidget(log_btn)
        row.addStretch(1)
        row.addWidget(repo_btn)

        tech = QLabel("PySide6 · PyGithub · GitPython · SQLite　|　MIT License")
        tech.setProperty("role", "faint")
        tech.setAlignment(Qt.AlignmentFlag.AlignCenter)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addLayout(head)
        layout.addWidget(desc)
        layout.addLayout(row)
        layout.addWidget(tech)
        layout.addWidget(buttons)
