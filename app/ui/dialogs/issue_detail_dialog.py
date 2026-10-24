"""Issue 详情：正文、评论流、评论 / 关闭 / 重开。"""
import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from app.core.workers import run_async


class IssueDetailDialog(QDialog):
    changed = Signal()

    def __init__(self, gh, owner_repo: str, number: int, can_write: bool = True, parent=None):
        super().__init__(parent)
        self.gh = gh
        self.owner_repo = owner_repo
        self.number = number
        self.can_write = can_write
        self.detail: dict | None = None
        self.setWindowTitle(f"Issue #{number} · {owner_repo}")
        self.resize(720, 620)

        self.title_label = QLabel("加载中…")
        self.title_label.setProperty("role", "h2")
        self.title_label.setWordWrap(True)
        self.state_chip = QLabel("")
        self.state_chip.setProperty("role", "chip")
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.title_label, stretch=1)
        head.addWidget(self.state_chip, alignment=Qt.AlignmentFlag.AlignTop)

        self.meta = QLabel("")
        self.meta.setProperty("role", "faint")
        self.meta.setWordWrap(True)

        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setPlaceholderText("（没有正文）")
        self.body.setMaximumHeight(140)

        self.comments_title = QLabel("评论")
        self.comments_title.setProperty("role", "section")
        self.comments = QTextBrowser()
        self.comments.setOpenExternalLinks(True)

        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setPlaceholderText("写下评论…（Ctrl+Enter 发送）")
        self.comment_edit.setFixedHeight(72)

        self.status = QLabel("")
        self.status.setProperty("role", "faint")

        self.send_btn = QPushButton("提交评论")
        self.send_btn.setProperty("variant", "primary")
        self.send_btn.clicked.connect(self._send_comment)
        self.state_btn = QPushButton("关闭 Issue")
        self.state_btn.setProperty("variant", "danger")
        self.state_btn.clicked.connect(self._toggle_state)
        open_btn = QPushButton("在浏览器打开")
        open_btn.setProperty("variant", "ghost")
        open_btn.clicked.connect(self._open_browser)

        actions = QHBoxLayout()
        actions.addWidget(open_btn)
        actions.addStretch(1)
        actions.addWidget(self.state_btn)
        actions.addWidget(self.send_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭窗口")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(self.meta)
        layout.addWidget(self.body)
        layout.addWidget(self.comments_title)
        layout.addWidget(self.comments, stretch=1)
        layout.addWidget(self.comment_edit)
        layout.addLayout(actions)
        layout.addWidget(self.status)
        layout.addWidget(buttons)

        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(seq), self.comment_edit)
            shortcut.activated.connect(self._send_comment)

        self._set_actions_enabled(False)
        run_async(lambda: gh.issue_detail(owner_repo, number),
                  on_ok=self._fill, on_err=self._failed)

    # ---------- 加载与渲染 ----------

    def _fill(self, detail: dict) -> None:
        self.detail = detail
        self.title_label.setText(f"#{detail['number']} {detail['title']}")
        state = "打开" if detail["state"] == "open" else "已关闭"
        self.state_chip.setText(state)
        self.state_chip.setProperty("tone", "success" if detail["state"] == "open" else "")
        self.state_chip.style().unpolish(self.state_chip)
        self.state_chip.style().polish(self.state_chip)

        bits = [f"{detail['author']} 创建" if detail["author"] else "",
                f"更新于 {detail['updated_at']}"]
        if detail["labels"]:
            bits.append("标签：" + "、".join(detail["labels"]))
        self.meta.setText(" · ".join(b for b in bits if b))
        self.body.setPlainText(detail["body"])
        self.comments_title.setText(f"评论 · {len(detail['comments'])}")
        self.comments.setHtml(self._comments_html(detail["comments"]))

        self.state_btn.setText("重开 Issue" if detail["state"] == "closed" else "关闭 Issue")
        self._set_actions_enabled(self.can_write)
        self.comment_edit.setEnabled(self.can_write)
        self.send_btn.setEnabled(self.can_write and bool(detail))
        if not self.can_write:
            self.status.setText("未配置 Token：当前为只读模式")

    @staticmethod
    def _comments_html(comments: list[dict]) -> str:
        from app.ui import theme
        faint = theme.tone("faint")
        if not comments:
            return f"<div style='color:{faint}; font-size:12px;'>还没有评论</div>"
        blocks = []
        for c in comments:
            body = html.escape(c["body"]).replace("\n", "<br>")
            author = html.escape(c["author"] or "未知用户")
            blocks.append(
                f"<p style='margin:0;'><b>{author}</b> "
                f"<span style='color:{faint}; font-size:11px;'>{c['created_at']}</span></p>"
                f"<p style='margin:0;'>{body}</p>"
                f"<p style='margin:0;'>&nbsp;</p>")
        return "".join(blocks)

    def _failed(self, err: str) -> None:
        self.title_label.setText("加载失败")
        self.status.setText(err)
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, ok: bool) -> None:
        self.send_btn.setEnabled(ok)
        self.state_btn.setEnabled(ok)

    # ---------- 操作 ----------

    def _send_comment(self) -> None:
        if not self.can_write or not self.comment_edit.toPlainText().strip():
            return
        text = self.comment_edit.toPlainText().strip()
        self._busy("正在提交评论…")

        def done(_):
            self.comment_edit.clear()
            self.changed.emit()
            self._reload("评论已提交")

        run_async(lambda: self.gh.add_comment(self.owner_repo, self.number, text),
                  on_ok=done, on_err=self._action_failed)

    def _toggle_state(self) -> None:
        if not self.can_write or not self.detail:
            return
        open_now = self.detail["state"] == "open"
        action = "关闭" if open_now else "重开"
        self._busy(f"正在{action} Issue…")

        def done(_):
            self.changed.emit()
            self._reload(f"Issue 已{action}")

        run_async(lambda: self.gh.set_issue_state(self.owner_repo, self.number, not open_now),
                  on_ok=done, on_err=self._action_failed)

    def _reload(self, message: str) -> None:
        self.status.setText(message)
        run_async(lambda: self.gh.issue_detail(self.owner_repo, self.number),
                  on_ok=self._fill, on_err=self._action_failed)

    def _busy(self, message: str) -> None:
        self.status.setText(message)
        self._set_actions_enabled(False)

    def _action_failed(self, err: str) -> None:
        self.status.setText(err)
        self._set_actions_enabled(self.can_write)
        self.send_btn.setEnabled(self.can_write)

    def _open_browser(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if self.detail:
            QDesktopServices.openUrl(QUrl(self.detail["url"]))
