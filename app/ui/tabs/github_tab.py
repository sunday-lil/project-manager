"""GitHub 面板 Tab：仓库概览 / Issues / Pull Requests。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from app.constants import SETTING_REPO_HISTORY
from app.core.settings import SettingsStore
from app.core.workers import run_async
from app.ui.dialogs.issue_create_dialog import IssueCreateDialog
from app.ui.dialogs.pr_detail_dialog import PrDetailDialog

_ISSUE_HEADERS = ["#", "标题", "标签", "作者", "更新"]
_PR_HEADERS = ["#", "标题", "分支", "作者", "状态", "更新"]


class GithubTab(QWidget):
    status_message = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.current_repo = ""

        # 顶部：仓库输入 + 加载
        self.repo_box = QComboBox()
        self.repo_box.setEditable(True)
        self.repo_box.setMinimumWidth(260)
        self.repo_box.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        self._load_history()
        self.load_btn = QPushButton("加载")
        self.load_btn.clicked.connect(self.load)

        top = QHBoxLayout()
        top.addWidget(QLabel("仓库（owner/repo）："))
        top.addWidget(self.repo_box, stretch=1)
        top.addWidget(self.load_btn)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_page(), "概览")
        self.tabs.addTab(self._build_issues_page(), "Issues")
        self.tabs.addTab(self._build_pr_page(), "Pull Requests")

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.tabs, stretch=1)

    # ---------- 页面构建 ----------

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        self.overview_form = QFormLayout(page)
        self.overview_labels = {}
        for key, title in (("description", "描述"), ("stars", "Star"), ("forks", "Fork"),
                           ("language", "主要语言"), ("default_branch", "默认分支"),
                           ("open_issues_count", "Open Issues（含 PR）"),
                           ("open_pulls_count", "Open PR"),
                           ("updated_at", "最近更新"), ("url", "链接")):
            label = QLabel("—")
            label.setTextInteractionFlags(Qt.TextInteractionFlags.TextBrowserInteraction)
            self.overview_labels[key] = label
            self.overview_form.addRow(title + "：", label)
        return page

    def _build_issues_page(self) -> QWidget:
        page = QWidget()
        self.issue_state = QComboBox()
        for s, label in (("open", "打开"), ("closed", "已关闭"), ("all", "全部")):
            self.issue_state.addItem(label, s)
        self.issue_state.currentIndexChanged.connect(lambda _: self._reload_issues())
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._reload_issues)
        self.issue_new_btn = QPushButton("＋ 新建")
        self.issue_new_btn.clicked.connect(self._new_issue)
        self.issue_close_btn = QPushButton("关闭")
        self.issue_close_btn.clicked.connect(lambda: self._set_issue_state(False))
        self.issue_reopen_btn = QPushButton("重开")
        self.issue_reopen_btn.clicked.connect(lambda: self._set_issue_state(True))
        self.issue_comment_btn = QPushButton("评论")
        self.issue_comment_btn.clicked.connect(self._comment_issue)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.issue_state)
        toolbar.addWidget(refresh)
        toolbar.addStretch(1)
        for b in (self.issue_new_btn, self.issue_close_btn, self.issue_reopen_btn, self.issue_comment_btn):
            toolbar.addWidget(b)

        self.issues_table = self._make_table(_ISSUE_HEADERS)
        self._set_issues_busy(False)  # 未加载仓库前禁用操作

        v = QVBoxLayout(page)
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
        refresh.clicked.connect(self._reload_pulls)
        self.pr_detail_btn = QPushButton("详情 / 合并")
        self.pr_detail_btn.clicked.connect(self._pr_detail)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.pr_state)
        toolbar.addWidget(refresh)
        toolbar.addStretch(1)
        toolbar.addWidget(self.pr_detail_btn)

        self.pulls_table = self._make_table(_PR_HEADERS)
        self._set_prs_busy(False)

        v = QVBoxLayout(page)
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
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return t

    # ---------- 加载 ----------

    def load_repo(self, owner_repo: str) -> None:
        """供其它 Tab 跳转：填入并加载指定仓库。"""
        self.repo_box.setCurrentText(owner_repo)
        self.load()

    def load(self) -> None:
        owner_repo = self.repo_box.currentText().strip()
        if not owner_repo or "/" not in owner_repo:
            self.status_message.emit("请输入 owner/repo 格式的仓库")
            return
        gh = self.ctx.service()
        if not self.ctx.has_token():
            self.status_message.emit("匿名模式：仅能读取公开仓库（未配置 Token）")
        self.current_repo = owner_repo
        self._set_issues_busy(False)
        self._set_prs_busy(False)
        self.load_btn.setEnabled(False)
        self.status_message.emit(f"正在加载 {owner_repo} …")

        def work():
            info = gh.get_repo_info(owner_repo)
            issues = gh.list_issues(owner_repo, "open")
            pulls = gh.list_pulls(owner_repo, "open")
            return info, issues, pulls

        run_async(work, on_ok=self._fill_all, on_err=self._load_failed)

    def _fill_all(self, result) -> None:
        info, issues, pulls = result
        for key, label in self.overview_labels.items():
            if key == "url":
                label.setText(f'<a href="{info["url"]}">{info["url"]}</a>')
                label.setOpenExternalLinks(True)
            elif key == "description":
                label.setWordWrap(True)
                label.setText(info[key])
            else:
                label.setText(str(info[key]))
        self._fill_issues(issues)
        self._fill_pulls(pulls)
        self._set_issues_busy(True)
        self._set_prs_busy(True)
        self.load_btn.setEnabled(True)
        self._save_history()
        self.status_message.emit(
            f"已加载 {self.current_repo}：{info['open_issues_count']} 个 open issues，{info['open_pulls_count']} 个 open PR")

    def _load_failed(self, err: str) -> None:
        self.load_btn.setEnabled(True)
        self.status_message.emit(err)

    # ---------- Issues ----------

    def _reload_issues(self) -> None:
        if not self.current_repo:
            return
        gh = self.ctx.service()
        state = self.issue_state.currentData()
        self._set_issues_busy(False)
        run_async(lambda: gh.list_issues(self.current_repo, state),
                  on_ok=self._fill_issues,
                  on_err=lambda e: (self.status_message.emit(e), self._set_issues_busy(True)))

    def _fill_issues(self, issues: list) -> None:
        self.issues_table.setRowCount(len(issues))
        for i, it in enumerate(issues):
            for j, v in enumerate((it["number"], it["title"], it["labels"],
                                   it["author"], it["updated_at"])):
                self.issues_table.setItem(i, j, QTableWidgetItem(str(v)))
        self._set_issues_busy(True)

    def _selected_issue(self) -> int | None:
        row = self.issues_table.currentRow()
        if row < 0:
            self.status_message.emit("请先在列表中选择一个 Issue")
            return None
        return int(self.issues_table.item(row, 0).text())

    def _set_issue_state(self, open_: bool) -> None:
        number = self._selected_issue()
        if number is None:
            return
        if not self.ctx.has_token():
            self.status_message.emit("此操作需要 Token，请先在设置中配置")
            return
        gh = self.ctx.service()
        action = "重开" if open_ else "关闭"
        self._set_issues_busy(False)
        run_async(lambda: gh.set_issue_state(self.current_repo, number, open_),
                  on_ok=lambda _: (self._reload_issues(),
                                   self.status_message.emit(f"Issue #{number} 已{action}")),
                  on_err=self._action_failed)

    def _comment_issue(self) -> None:
        number = self._selected_issue()
        if number is None:
            return
        if not self.ctx.has_token():
            self.status_message.emit("此操作需要 Token，请先在设置中配置")
            return
        gh = self.ctx.service()
        text, ok = QInputDialog.getMultiLineText(self, "添加评论", f"Issue #{number} 的评论内容：")
        if not ok or not text.strip():
            return
        self._set_issues_busy(False)
        run_async(lambda: gh.add_comment(self.current_repo, number, text.strip()),
                  on_ok=lambda _: (self._set_issues_busy(True),
                                   self.status_message.emit(f"已评论 Issue #{number}")),
                  on_err=self._action_failed)

    def _new_issue(self) -> None:
        if not self.current_repo:
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
                  on_ok=self._fill_pulls,
                  on_err=lambda e: (self.status_message.emit(e), self._set_prs_busy(True)))

    def _fill_pulls(self, pulls: list) -> None:
        self.pulls_table.setRowCount(len(pulls))
        for i, p in enumerate(pulls):
            state = "已合并" if p["merged"] else ("草稿" if p["draft"] else p["state"])
            for j, v in enumerate((p["number"], p["title"], p["branch"],
                                   p["author"], state, p["updated_at"])):
                self.pulls_table.setItem(i, j, QTableWidgetItem(str(v)))
        self._set_prs_busy(True)

    def _selected_pull(self) -> dict | None:
        row = self.pulls_table.currentRow()
        if row < 0:
            self.status_message.emit("请先在列表中选择一个 PR")
            return None
        number = int(self.pulls_table.item(row, 0).text())
        return {"number": number, "title": self.pulls_table.item(row, 1).text(),
                "branch": self.pulls_table.item(row, 2).text(),
                "author": self.pulls_table.item(row, 3).text(),
                "state": "open" if self.pulls_table.item(row, 4).text() not in ("已合并", "closed") else "closed",
                "merged": self.pulls_table.item(row, 4).text() == "已合并",
                "draft": self.pulls_table.item(row, 4).text() == "草稿",
                "updated_at": self.pulls_table.item(row, 5).text(),
                "url": f"https://github.com/{self.current_repo}/pull/{number}"}

    def _pr_detail(self) -> None:
        pr = self._selected_pull()
        if pr is None:
            return
        dlg = PrDetailDialog(self.current_repo, pr, self)
        result = dlg.exec()
        if result == 2:  # 合并
            if not self.ctx.has_token():
                self.status_message.emit("此操作需要 Token，请先在设置中配置")
                return
            gh = self.ctx.service()
            method = dlg.merge_box.currentData()
            self._set_prs_busy(False)
            run_async(lambda: gh.merge_pull(self.current_repo, pr["number"], method),
                      on_ok=lambda _: (self._reload_pulls(),
                                       self.status_message.emit(f"PR #{pr['number']} 已合并")),
                      on_err=self._action_failed)
        elif result == 3:  # 关闭 PR
            if not self.ctx.has_token():
                self.status_message.emit("此操作需要 Token，请先在设置中配置")
                return
            gh = self.ctx.service()
            self._set_prs_busy(False)
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
        for b in (self.issue_new_btn, self.issue_close_btn, self.issue_reopen_btn, self.issue_comment_btn):
            b.setEnabled(ready)

    def _set_prs_busy(self, ready: bool) -> None:
        self.pr_detail_btn.setEnabled(ready)

    def _load_history(self) -> None:
        history = (SettingsStore.get(SETTING_REPO_HISTORY) or "").split(",")
        self.repo_box.addItems([h for h in history if h.strip()])

    def _save_history(self) -> None:
        history = [self.repo_box.itemText(i) for i in range(self.repo_box.count())]
        history = [h for h in history if h.strip()][:10]
        if self.current_repo not in history:
            history.insert(0, self.current_repo)
        SettingsStore.set(SETTING_REPO_HISTORY, ",".join(history[:10]))
