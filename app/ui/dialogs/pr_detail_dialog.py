"""PR 详情对话框：信息展示 + 合并 / 关闭。"""
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.constants import MERGE_METHOD_LABELS, MERGE_METHODS, SETTING_MERGE_METHOD
from app.core.settings import SettingsStore


class PrDetailDialog(QDialog):
    def __init__(self, owner_repo: str, pr: dict, parent=None):
        super().__init__(parent)
        self.owner_repo = owner_repo
        self.pr = pr
        self.setWindowTitle(f"PR #{pr['number']} · {owner_repo}")
        self.setMinimumWidth(560)

        info = QFormLayout()
        self.title_label = QLabel(pr["title"])
        self.title_label.setWordWrap(True)
        self.title_label.setProperty("role", "h2")
        info.addRow("标题", self.title_label)
        info.addRow("分支", QLabel(pr["branch"]))
        info.addRow("作者", QLabel(pr["author"]))
        state = ("已合并" if pr.get("merged") else
                 ("草稿" if pr.get("draft") else
                  ("打开" if pr["state"] == "open" else "已关闭")))
        info.addRow("状态", QLabel(state))
        info.addRow("更新", QLabel(pr["updated_at"]))
        link = QLabel(f'<a href="{pr["url"]}">在 GitHub 上查看</a>')
        link.setOpenExternalLinks(True)
        info.addRow("", link)

        body = QPlainTextEdit(pr.get("body", ""))
        body.setReadOnly(True)
        body.setPlaceholderText("（没有描述）")
        body.setMaximumHeight(120)

        self.merge_box = QComboBox()
        for m in MERGE_METHODS:
            self.merge_box.addItem(MERGE_METHOD_LABELS[m], m)
        saved = SettingsStore.get(SETTING_MERGE_METHOD)
        if saved in MERGE_METHODS:
            self.merge_box.setCurrentIndex(MERGE_METHODS.index(saved))

        self.merge_btn = QPushButton("合并 PR")
        self.merge_btn.setProperty("variant", "primary")
        self.merge_btn.clicked.connect(self._merge)
        self.close_btn = QPushButton("关闭 PR")
        self.close_btn.setProperty("variant", "danger")
        self.close_btn.clicked.connect(self._close)
        can_act = pr["state"] == "open" and not pr.get("merged")
        self.merge_btn.setEnabled(can_act)
        self.close_btn.setEnabled(can_act)
        self.merge_box.setEnabled(can_act)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("合并方式"))
        actions.addWidget(self.merge_box)
        actions.addStretch(1)
        actions.addWidget(self.close_btn)
        actions.addWidget(self.merge_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭窗口")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(8)
        layout.addLayout(info)
        layout.addWidget(QLabel("描述"))
        layout.addWidget(body)
        layout.addLayout(actions)
        layout.addWidget(buttons)

    def _merge(self) -> None:
        self.done(2)  # 2 = 请求合并

    def _close(self) -> None:
        self.done(3)  # 3 = 请求关闭 PR
