"""GitHub 面板：仓库概览 / Issues / Pull Requests。"""
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.constants import SETTING_REPO_HISTORY
from app.core.settings import SettingsStore
from app.core.workers import run_async
from app.services import repo_service
from app.ui import theme
from app.ui.dialogs.issue_create_dialog import IssueCreateDialog
from app.ui.dialogs.issue_detail_dialog import IssueDetailDialog
from app.ui.dialogs.pr_detail_dialog import PrDetailDialog
from app.ui.widgets.common import PageHeader

_ISSUE_HEADERS = ["#", "状态", "标题", "标签", "作者", "更新"]
_PR_HEADERS = ["#", "标题", "分支", "作者", "状态", "更新"]


class _SummaryRow(QFrame):
    """概览里的可点击摘要行。"""

    activated = Signal(object)

    def __init__(self, number: int, title: str, meta: str, payload: dict, parent=None):
        super().__init__(parent)
        self.payload = payload
        self.setProperty("role", "row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(title)
        num = QLabel(f"#{number}")
        num.setProperty("role", "chip")
        title_label = QLabel(title)
        title_label.setProperty("role", "rowTitle")
        meta_label = QLabel(meta)
        meta_label.setProperty("role", "faint")
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(title_label)
        text.addWidget(meta_label)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(8)
        row.addWidget(num, alignment=Qt.AlignmentFlag.AlignTop)
        row.addLayout(text, stretch=1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.payload)
        super().mouseReleaseEvent(event)


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class GithubTab(QWidget):
    status_message = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self.current_repo = ""
        self._repo_info: dict | None = None
        self._issues: list[dict] = []
        self._pulls: list[dict] = []

        self.header = PageHeader("GitHub", "在同一个窗口里处理远端事务")
        self.mode_chip = QLabel("")
        self.mode_chip.setProperty("role", "chip")
        self.header.add_action(self.mode_chip)
        self.refresh_token_state()

        self.repo_box = QComboBox()
        self.repo_box.setEditable(True)
        self.repo_box.setMinimumWidth(280)
        self.repo_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.repo_box.lineEdit().setPlaceholderText("owner/repo")
        self.repo_box.lineEdit().returnPressed.connect(self.load)
        self._fill_repo_choices()
        self.load_btn = QPushButton("加载")
        self.load_btn.setProperty("variant", "primary")
        self.load_btn.clicked.connect(self.load)
        self.browser_btn = QPushButton("在浏览器打开")
        self.browser_btn.setProperty("variant", "ghost")
        self.browser_btn.setEnabled(False)
        self.browser_btn.clicked.connect(self._open_in_browser)

        picker = QHBoxLayout()
        picker.setSpacing(8)
        picker.addWidget(QLabel("仓库"))
        picker.addWidget(self.repo_box, stretch=1)
        picker.addWidget(self.load_btn)
        picker.addWidget(self.browser_btn)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_page(), "概览")
        self.tabs.addTab(self._build_issues_page(), "Issues")
        self.tabs.addTab(self._build_pr_page(), "Pull Requests")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)
        root.addWidget(self.header)
        root.addLayout(picker)
        root.addWidget(self.tabs, stretch=1)
        self.refresh_token_state()

    # ---------- 页面构建 ----------

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 16, 0, 0)
        outer.setSpacing(14)

        left = QFrame()
        left.setProperty("role", "card")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(20, 18, 20, 18)
        lv.setSpacing(10)

        self.overview_desc = QLabel("加载仓库后显示描述")
        self.overview_desc.setProperty("role", "h2")
        self.overview_desc.setWordWrap(True)
        lv.addWidget(self.overview_desc)

        self.ov_language = QLabel("—")
        self.ov_stars = QLabel("—")
        self.ov_forks = QLabel("—")
        for chip in (self.ov_language, self.ov_stars, self.ov_forks):
            chip.setProperty("role", "chip")
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for chip in (self.ov_language, self.ov_stars, self.ov_forks):
            chips.addWidget(chip)
        chips.addStretch(1)
        lv.addLayout(chips)

        divider = QFrame()
        divider.setProperty("role", "hline")
        lv.addWidget(divider)

        form = QFormLayout()
        form.setVerticalSpacing(9)
        self.overview_labels: dict[str, QLabel] = {}
        for key, title in (("default_branch", "默认分支"),
                           ("open_issues_count", "Open Issues（含 PR）"),
                           ("open_pulls_count", "Open PR"),
                           ("updated_at", "最近更新"), ("url", "链接")):
            label = QLabel("—")
            label.setTextInteractionFlags(Qt.TextInteractionFlags.TextBrowserInteraction)
            self.overview_labels[key] = label
            form.addRow(title, label)
        lv.addLayout(form)

        divider3 = QFrame()
        divider3.setProperty("role", "hline")
        lv.addWidget(divider3)
        recent_issues = QLabel("最近 Issues")
        recent_issues.setProperty("role", "section")
        lv.addWidget(recent_issues)
        self.ov_issues_box = QVBoxLayout()
        self.ov_issues_box.setSpacing(0)
        lv.addLayout(self.ov_issues_box)
        lv.addStretch(1)

        right = QFrame()
        right.setProperty("role", "card")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(20, 18, 20, 18)
        rv.setSpacing(12)

        remote = QLabel("远端概览")
        remote.setProperty("role", "section")
        rv.addWidget(remote)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        issue_box, self.ov_issue_big = self._mini_stat("Open Issues", "accent")
        pr_box, self.ov_pr_big = self._mini_stat("Open PR", "warning")
        stats.addWidget(issue_box, stretch=1)
        stats.addWidget(pr_box, stretch=1)
        rv.addLayout(stats)

        jump = QHBoxLayout()
        jump.setSpacing(8)
        issues_btn = QPushButton("查看 Issues")
        issues_btn.setProperty("variant", "ghost")
        issues_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        pr_btn = QPushButton("查看 Pull Requests")
        pr_btn.setProperty("variant", "ghost")
        pr_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        jump.addWidget(issues_btn)
        jump.addWidget(pr_btn)
        jump.addStretch(1)
        rv.addLayout(jump)

        divider2 = QFrame()
        divider2.setProperty("role", "hline")
        rv.addWidget(divider2)

        actions = QLabel("快捷操作")
        actions.setProperty("role", "section")
        rv.addWidget(actions)

        self.overview_new_btn = QPushButton("＋ 新建 Issue")
        self.overview_new_btn.setProperty("variant", "primary")
        self.overview_new_btn.clicked.connect(self._new_issue)
        rv.addWidget(self.overview_new_btn)

        refresh_btn = QPushButton("刷新仓库数据")
        refresh_btn.clicked.connect(self.load)
        rv.addWidget(refresh_btn)

        divider3 = QFrame()
        divider3.setProperty("role", "hline")
        rv.addWidget(divider3)
        recent_pulls = QLabel("最近 Pull Requests")
        recent_pulls.setProperty("role", "section")
        rv.addWidget(recent_pulls)
        self.ov_pulls_box = QVBoxLayout()
        self.ov_pulls_box.setSpacing(0)
        rv.addLayout(self.ov_pulls_box)

        hint = QLabel("匿名模式每小时 60 次请求，配置 Token 后为 5000 次。")
        hint.setProperty("role", "faint")
        hint.setWordWrap(True)
        rv.addWidget(hint)
        rv.addStretch(1)

        outer.addWidget(left, stretch=3)
        outer.addWidget(right, stretch=2)
        return page

    @staticmethod
    def _mini_stat(title: str, tone: str) -> tuple[QFrame, QLabel]:
        box = QFrame()
        box.setProperty("role", "inset")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)
        label = QLabel(title)
        label.setProperty("role", "faint")
        value = QLabel("—")
        value.setProperty("role", "stat")
        value.setProperty("tone", tone)
        layout.addWidget(label)
        layout.addWidget(value)
        return box, value

    def _build_issues_page(self) -> QWidget:
        page = QWidget()
        self.issue_state = QComboBox()
        for s, label in (("open", "打开"), ("closed", "已关闭"), ("all", "全部")):
            self.issue_state.addItem(label, s)
        self.issue_state.currentIndexChanged.connect(lambda _: self._reload_issues())

        self.issue_search = QLineEdit()
        self.issue_search.setPlaceholderText("筛选标题、标签、编号…")
        self.issue_search.setClearButtonEnabled(True)
        self.issue_search.textChanged.connect(lambda _: self._fill_issues(self._issues))

        refresh = QPushButton("刷新")
        refresh.setProperty("variant", "ghost")
        refresh.clicked.connect(self._reload_issues)
        self.issue_new_btn = QPushButton("＋ 新建")
        self.issue_new_btn.clicked.connect(self._new_issue)
        self.issue_detail_btn = QPushButton("详情")
        self.issue_detail_btn.clicked.connect(self._open_issue_detail)
        self.issue_close_btn = QPushButton("关闭")
        self.issue_close_btn.clicked.connect(lambda: self._set_issue_state(False))
        self.issue_reopen_btn = QPushButton("重开")
        self.issue_reopen_btn.clicked.connect(lambda: self._set_issue_state(True))

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(self.issue_state)
        toolbar.addWidget(self.issue_search, stretch=1)
        toolbar.addWidget(refresh)
        toolbar.addWidget(self.issue_new_btn)
        toolbar.addWidget(self.issue_detail_btn)
        toolbar.addWidget(self.issue_close_btn)
        toolbar.addWidget(self.issue_reopen_btn)

        self.issues_table = self._make_table(_ISSUE_HEADERS)
        self.issues_table.doubleClicked.connect(self._open_issue_detail)
        self._set_issues_busy(False)

        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)
        v.addLayout(toolbar)
        v.addWidget(self.issues_table, stretch=1)
        return page

    def _build_pr_page(self) -> QWidget:
        page = QWidget()
        self.pr_state = QComboBox()
        for s, label in (("open", "打开"), ("closed", "已关闭"), ("all", "全部")):
            self.pr_state.addItem(label, s)
        self.pr_state.currentIndexChanged.connect(lambda _: self._reload_pulls())
        refresh = QPushButton("刷新")
        refresh.setProperty("variant", "ghost")
        refresh.clicked.connect(self._reload_pulls)
        self.pr_detail_btn = QPushButton("详情 / 合并")
        self.pr_detail_btn.clicked.connect(self._pr_detail)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(self.pr_state)
        toolbar.addStretch(1)
        toolbar.addWidget(refresh)
        toolbar.addWidget(self.pr_detail_btn)

        self.pulls_table = self._make_table(_PR_HEADERS)
        self.pulls_table.doubleClicked.connect(self._pr_detail)
        self._set_prs_busy(False)

        v = QVBoxLayout(page)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(10)
        v.addLayout(toolbar)
        v.addWidget(self.pulls_table, stretch=1)
        return page

    @staticmethod
    def _make_table(headers: list) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        t.setShowGrid(False)
        t.setAlternatingRowColors(True)
        header = t.horizontalHeader()
        for i in (0, 1, 3, 4, 5):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        return t

    # ---------- 仓库选择 ----------

    def refresh_token_state(self) -> None:
        if self.ctx.has_token():
            self.mode_chip.setText("已连接")
            self.mode_chip.setProperty("tone", "success")
        else:
            self.mode_chip.setText("匿名只读")
            self.mode_chip.setProperty("tone", "warning")
        theme.repolish(self.mode_chip)
        for attr in ("issue_new_btn", "overview_new_btn"):
            if hasattr(self, attr):
                getattr(self, attr).setEnabled(self.ctx.has_token())

    def refresh_repos(self) -> None:
        """本地仓库变化后刷新选择列表（保留当前输入）。"""
        current = self.repo_box.currentText()
        self._fill_repo_choices()
        self.repo_box.setCurrentText(current)

    def restyle(self) -> None:
        """主题切换后重绘依赖语义色的表格。"""
        self.refresh_token_state()
        if self._repo_info:
            self._fill_overview(self._repo_info)
        self._fill_issues(self._issues)
        self._fill_pulls(self._pulls)

    def _fill_repo_choices(self) -> None:
        seen: list[str] = []
        for r in repo_service.list_repos():
            if r.owner_repo and r.owner_repo not in seen:
                seen.append(r.owner_repo)
        history = [h.strip() for h in (SettingsStore.get(SETTING_REPO_HISTORY) or "").split(",")
                   if h.strip()]
        self.repo_box.blockSignals(True)
        self.repo_box.clear()
        for item in seen + [h for h in history if h not in seen]:
            self.repo_box.addItem(item)
        self.repo_box.blockSignals(False)

    def load_repo(self, owner_repo: str) -> None:
        """供其它页面跳转：填入并加载指定仓库。"""
        self.repo_box.setCurrentText(owner_repo)
        self.load()

    def load(self) -> None:
        owner_repo = self.repo_box.currentText().strip()
        if not owner_repo or "/" not in owner_repo:
            self.status_message.emit("请输入 owner/repo 格式的仓库")
            return
        gh = self.ctx.service()
        self.current_repo = owner_repo
        self.load_btn.setEnabled(False)
        self.browser_btn.setEnabled(False)
        self._set_issues_busy(False)
        self._set_prs_busy(False)
        self.status_message.emit(f"正在加载 {owner_repo} …")

        def work():
            info = gh.get_repo_info(owner_repo)
            issues = gh.list_issues(owner_repo, "open")
            pulls = gh.list_pulls(owner_repo, "open")
            return info, issues, pulls

        run_async(work, on_ok=self._fill_all, on_err=self._load_failed)

    def _load_failed(self, err: str) -> None:
        self.load_btn.setEnabled(True)
        self._set_issues_busy(False)
        self._set_prs_busy(False)
        self.status_message.emit(err)

    def _fill_all(self, result) -> None:
        info, issues, pulls = result
        self._repo_info = info
        self._fill_overview(info)
        self._fill_overview_issues(issues)
        self._fill_overview_pulls(pulls)
        self._issues = issues
        self._pulls = pulls
        self._fill_issues(issues)
        self._fill_pulls(pulls)
        self._set_issues_busy(True)
        self._set_prs_busy(True)
        self.load_btn.setEnabled(True)
        self.browser_btn.setEnabled(True)
        self._save_history()
        self.header.set_subtitle(f"{self.current_repo} · 已同步远端数据")
        self.status_message.emit(
            f"已加载 {self.current_repo}：{info['open_issues_count']} 个 open issues，"
            f"{info['open_pulls_count']} 个 open PR")

    def _fill_overview(self, info: dict) -> None:
        self.overview_desc.setText(info["description"])
        self.ov_language.setText(f'语言 {info["language"]}')
        self.ov_stars.setText(f'Star {info["stars"]}')
        self.ov_forks.setText(f'Fork {info["forks"]}')
        self.ov_issue_big.setText(str(info["open_issues_count"]))
        self.ov_pr_big.setText(str(info["open_pulls_count"]))
        for key, label in self.overview_labels.items():
            if key == "url":
                label.setText(f'<a href="{info["url"]}">{info["url"]}</a>')
                label.setOpenExternalLinks(True)
            else:
                label.setText(str(info[key]))

    def _fill_overview_issues(self, issues: list) -> None:
        _clear_layout(self.ov_issues_box)
        if not issues:
            empty = QLabel("暂无打开的 Issue")
            empty.setProperty("role", "empty")
            self.ov_issues_box.addWidget(empty)
            return
        for it in issues[:3]:
            row = _SummaryRow(it["number"], it["title"],
                              f"{it['author'] or '未知'} · {it['updated_at']}", it)
            row.activated.connect(self._show_issue)
            self.ov_issues_box.addWidget(row)

    def _fill_overview_pulls(self, pulls: list) -> None:
        _clear_layout(self.ov_pulls_box)
        if not pulls:
            empty = QLabel("暂无打开的 PR")
            empty.setProperty("role", "empty")
            self.ov_pulls_box.addWidget(empty)
            return
        for pr in pulls[:2]:
            row = _SummaryRow(pr["number"], pr["title"],
                              f"{pr['branch']} · {pr['updated_at']}", pr)
            row.activated.connect(self._show_pr)
            self.ov_pulls_box.addWidget(row)

    def _open_in_browser(self) -> None:
        if self._repo_info:
            QDesktopServices.openUrl(QUrl(self._repo_info["url"]))

    # ---------- Issues ----------

    def _reload_issues(self) -> None:
        if not self.current_repo:
            return
        gh = self.ctx.service()
        state = self.issue_state.currentData()
        self._set_issues_busy(False)
        run_async(lambda: gh.list_issues(self.current_repo, state),
                  on_ok=self._store_issues,
                  on_err=lambda e: (self.status_message.emit(e), self._set_issues_busy(True)))

    def _store_issues(self, issues: list) -> None:
        self._issues = issues
        self._fill_issues(issues)
        self._fill_overview_issues(issues)
        self._set_issues_busy(True)

    def _fill_issues(self, issues: list) -> None:
        query = self.issue_search.text().strip().lower()
        rows = [it for it in issues
                if not query
                or query in it["title"].lower()
                or query in it["labels"].lower()
                or query in it["author"].lower()
                or query in str(it["number"])]
        self.issues_table.setRowCount(len(rows))
        for i, it in enumerate(rows):
            state = "打开" if it["state"] == "open" else "已关闭"
            values = (f"#{it['number']}", state, it["title"],
                      it["labels"], it["author"], it["updated_at"])
            for j, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if j == 0:
                    item.setData(Qt.ItemDataRole.UserRole, it)
                self.issues_table.setItem(i, j, item)

    def _selected_issue(self) -> dict | None:
        row = self.issues_table.currentRow()
        if row < 0:
            self.status_message.emit("请先在列表中选择一个 Issue")
            return None
        item = self.issues_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_issue_detail(self) -> None:
        issue = self._selected_issue()
        if issue is not None:
            self._show_issue(issue)

    def _show_issue(self, issue: dict) -> None:
        if not self.current_repo:
            return
        dlg = IssueDetailDialog(self.ctx.service(), self.current_repo,
                                issue["number"], self.ctx.has_token(), self)
        dlg.changed.connect(self._reload_issues)
        dlg.exec()

    def _set_issue_state(self, open_: bool) -> None:
        issue = self._selected_issue()
        if issue is None:
            return
        if not self.ctx.has_token():
            self.status_message.emit("此操作需要 Token，请先在设置中配置")
            return
        gh = self.ctx.service()
        action = "重开" if open_ else "关闭"
        self._set_issues_busy(False)
        run_async(lambda: gh.set_issue_state(self.current_repo, issue["number"], open_),
                  on_ok=lambda _: (self._reload_issues(),
                                   self.status_message.emit(f"Issue #{issue['number']} 已{action}")),
                  on_err=self._action_failed)

    def _new_issue(self) -> None:
        if not self.current_repo:
            self.status_message.emit("请先加载一个仓库")
            return
        if not self.ctx.has_token():
            self.status_message.emit("此操作需要 Token，请先在设置中配置")
            return
        gh = self.ctx.service()
        dlg = IssueCreateDialog(self.current_repo, self)
        if dlg.exec() != IssueCreateDialog.DialogCode.Accepted:
            return
        title, body, labels = dlg.values()
        self._set_issues_busy(False)
        run_async(lambda: gh.create_issue(self.current_repo, title, body, labels),
                  on_ok=lambda r: (self._reload_issues(),
                                   self.status_message.emit(f"已创建 Issue #{r['number']}")),
                  on_err=self._action_failed)

    # ---------- Pull Requests ----------

    def _reload_pulls(self) -> None:
        if not self.current_repo:
            return
        gh = self.ctx.service()
        state = self.pr_state.currentData()
        self._set_prs_busy(False)
        run_async(lambda: gh.list_pulls(self.current_repo, state),
                  on_ok=self._store_pulls,
                  on_err=lambda e: (self.status_message.emit(e), self._set_prs_busy(True)))

    def _store_pulls(self, pulls: list) -> None:
        self._pulls = pulls
        self._fill_pulls(pulls)
        self._fill_overview_pulls(pulls)
        self._set_prs_busy(True)

    def _fill_pulls(self, pulls: list) -> None:
        self.pulls_table.setRowCount(len(pulls))
        for i, p in enumerate(pulls):
            state = ("已合并" if p["merged"] else
                     ("草稿" if p["draft"] else ("打开" if p["state"] == "open" else "已关闭")))
            values = (f"#{p['number']}", p["title"], p["branch"], p["author"], state, p["updated_at"])
            for j, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if j == 0:
                    item.setData(Qt.ItemDataRole.UserRole, p)
                if j == 4:
                    if state == "已合并":
                        item.setForeground(QColor(theme.tone("success")))
                    elif state == "已关闭":
                        item.setForeground(QColor(theme.tone("faint")))
                    elif state == "打开":
                        item.setForeground(QColor(theme.tone("accent")))
                self.pulls_table.setItem(i, j, item)

    def _selected_pull(self) -> dict | None:
        row = self.pulls_table.currentRow()
        if row < 0:
            self.status_message.emit("请先在列表中选择一个 PR")
            return None
        item = self.pulls_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _pr_detail(self) -> None:
        pr = self._selected_pull()
        if pr is not None:
            self._show_pr(pr)

    def _show_pr(self, pr: dict) -> None:
        if not self.current_repo:
            return
        dlg = PrDetailDialog(self.current_repo, pr, self)
        result = dlg.exec()
        if result not in (2, 3):
            return
        if not self.ctx.has_token():
            self.status_message.emit("此操作需要 Token，请先在设置中配置")
            return
        gh = self.ctx.service()
        self._set_prs_busy(False)
        if result == 2:
            method = dlg.merge_box.currentData()
            run_async(lambda: gh.merge_pull(self.current_repo, pr["number"], method),
                      on_ok=lambda _: (self._reload_pulls(),
                                       self.status_message.emit(f"PR #{pr['number']} 已合并")),
                      on_err=self._action_failed)
        else:
            run_async(lambda: gh.close_pull(self.current_repo, pr["number"]),
                      on_ok=lambda _: (self._reload_pulls(),
                                       self.status_message.emit(f"PR #{pr['number']} 已关闭")),
                      on_err=self._action_failed)

    # ---------- 通用 ----------

    def _action_failed(self, err: str) -> None:
        self._set_issues_busy(True)
        self._set_prs_busy(True)
        self.status_message.emit(err)

    def _set_issues_busy(self, ready: bool) -> None:
        enabled = ready and self.ctx.has_token()
        for b in (self.issue_close_btn, self.issue_reopen_btn,
                  self.issue_new_btn):
            b.setEnabled(enabled)
        self.issue_detail_btn.setEnabled(ready)

    def _set_prs_busy(self, ready: bool) -> None:
        self.pr_detail_btn.setEnabled(ready)

    def _save_history(self) -> None:
        if not self.current_repo:
            return
        history = [self.repo_box.itemText(i) for i in range(self.repo_box.count())]
        history = [h for h in history if h.strip()]
        if self.current_repo in history:
            history.remove(self.current_repo)
        history.insert(0, self.current_repo)
        SettingsStore.set(SETTING_REPO_HISTORY, ",".join(history[:10]))
