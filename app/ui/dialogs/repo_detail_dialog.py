"""仓库详情对话框：基本信息 + 分支列表 + 最近提交。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout)

from app.core.workers import run_async
from app.models.repo import LocalRepo
from app.services import repo_service


class RepoDetailDialog(QDialog):
    def __init__(self, repo: LocalRepo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle(f"仓库详情 - {repo.name}")
        self.resize(680, 480)

        info = QFormLayout()
        info.addRow("路径：", QLabel(repo.path))
        info.addRow("远程：", QLabel(repo.remote_url or "（无远程）"))
        self.branch_label = QLabel("读取中…")
        info.addRow("当前分支：", self.branch_label)
        self.remote_label = QLabel("—")
        info.addRow("GitHub：", self.remote_label)
        self.remote_label.setTextInteractionFlags(Qt.TextInteractionFlags.TextBrowserInteraction)
        self.remote_label.setTextFormat(Qt.TextFormat.RichText)
        if repo.owner_repo:
            url = f"https://github.com/{repo.owner_repo}"
            self.remote_label.setText(f'<a href="{url}">{repo.owner_repo}</a>')
            self.remote_label.setOpenExternalLinks(True)

        self.tabs = QTabWidget()
        self.commits_table = self._make_table(["提交", "说明", "作者", "时间"])
        self.branches_table = self._make_table(["分支", "类型"])
        self.tabs.addTab(self.commits_table, "最近提交")
        self.tabs.addTab(self.branches_table, "分支")

        layout = QVBoxLayout(self)
        layout.addLayout(info)
        layout.addWidget(self.tabs, stretch=1)
        self._load()

    @staticmethod
    def _make_table(headers: list) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return t

    def _load(self) -> None:
        def work():
            status = repo_service.get_status(self.repo.path)
            commits = repo_service.recent_commits(self.repo.path)
            local, remote = repo_service.branches(self.repo.path)
            return status, commits, local, remote

        run_async(work, on_ok=self._fill, on_err=lambda e: self.branch_label.setText(f"读取失败：{e}"))

    def _fill(self, result) -> None:
        status, commits, local, remote = result
        self.branch_label.setText(status.branch + ("（有未提交更改）" if status.is_dirty else ""))

        self.commits_table.setRowCount(len(commits))
        for i, c in enumerate(commits):
            for j, v in enumerate((c["sha"], c["message"], c["author"], c["time"])):
                self.commits_table.setItem(i, j, QTableWidgetItem(str(v)))

        rows = [(b, "本地") for b in local] + [(b, "远程") for b in remote]
        self.branches_table.setRowCount(len(rows))
        for i, (b, t) in enumerate(rows):
            self.branches_table.setItem(i, 0, QTableWidgetItem(b))
            self.branches_table.setItem(i, 1, QTableWidgetItem(t))
