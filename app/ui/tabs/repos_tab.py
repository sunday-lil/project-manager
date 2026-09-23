"""本地仓库管理 Tab：扫描、状态表格、详情、右键操作。"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QMenu, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from app.core.settings import SettingsStore
from app.core.workers import run_async
from app.models.repo import LocalRepo
from app.services import repo_service, workspace_service
from app.ui.dialogs.repo_detail_dialog import RepoDetailDialog

_HEADERS = ["名称", "分支", "未提交更改", "领先", "落后", "路径"]


class ReposTab(QWidget):
    status_message = Signal(str)
    repos_changed = Signal()  # 仓库列表变化（扫描完成），通知其它 Tab 联动刷新
    view_on_github = Signal(str)  # owner_repo，主窗口转发给 GitHub Tab

    def __init__(self, parent=None):
        super().__init__(parent)

        self.scan_btn = QPushButton("📂 添加扫描目录")
        self.scan_btn.clicked.connect(self._scan)
        refresh_btn = QPushButton("🔄 刷新状态")
        refresh_btn.clicked.connect(self.refresh)
        fetch_btn = QPushButton("⬇ fetch 全部")
        fetch_btn.clicked.connect(self._fetch_all)
        self.summary = QLabel("")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.scan_btn)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(fetch_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.summary)

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(self._detail)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        root = QVBoxLayout(self)
        root.addLayout(toolbar)
        root.addWidget(self.table, stretch=1)
        self.refresh()

    # ---------- 数据加载 ----------

    def refresh(self) -> None:
        repos = repo_service.list_repos()
        self.table.setRowCount(len(repos))
        for i, repo in enumerate(repos):
            it = QTableWidgetItem(repo.name or repo.path)
            it.setData(Qt.ItemDataRole.UserRole, repo.id)
            self.table.setItem(i, 0, it)
            for j in range(1, 6):
                self.table.setItem(i, j, QTableWidgetItem("…"))
        self.summary.setText(f"共 {len(repos)} 个仓库" + ("" if repos else "（点击「选择根目录并扫描」开始）"))
        if repos:
            self._fill_statuses()

    def _fill_statuses(self) -> None:
        def work():
            return repo_service.all_statuses()

        def fill(pairs):
            if self.table.rowCount() != len(pairs):
                self.refresh()  # 期间表格被重建，放弃本次结果
                return
            for i, (repo, st) in enumerate(pairs):
                self.table.item(i, 5).setText(repo.path)
                if st.error:
                    self.table.setItem(i, 1, QTableWidgetItem(st.error))
                    self.table.setItem(i, 2, QTableWidgetItem("—"))
                    self.table.setItem(i, 3, QTableWidgetItem("—"))
                    self.table.setItem(i, 4, QTableWidgetItem("—"))
                    continue
                self.table.setItem(i, 1, QTableWidgetItem(st.branch))
                dirty = QTableWidgetItem("有" if st.is_dirty else "干净")
                if st.is_dirty:
                    dirty.setForeground(Qt.GlobalColor.red)
                self.table.setItem(i, 2, dirty)
                ahead = "—" if st.ahead is None else str(st.ahead)
                behind = "—" if st.behind is None else str(st.behind)
                self.table.setItem(i, 3, QTableWidgetItem(ahead))
                self.table.setItem(i, 4, QTableWidgetItem(behind))
            self.status_message.emit("仓库状态已刷新")

        run_async(work, on_ok=fill, on_err=lambda e: self.status_message.emit(f"刷新失败：{e}"))

    # ---------- 操作 ----------

    def _scan(self) -> None:
        roots = SettingsStore.get_scan_roots()
        default = roots[-1] if roots else ""
        path = QFileDialog.getExistingDirectory(self, "选择要添加的扫描目录", default)
        if not path:
            return
        if path not in roots:
            roots.append(path)
        SettingsStore.set_scan_roots(roots)
        self._run_scan(roots)

    def rescan(self) -> None:
        """按已保存的根目录列表重新扫描（设置保存后调用）。"""
        roots = SettingsStore.get_scan_roots()
        if roots:
            self._run_scan(roots)

    def _run_scan(self, roots: list[str]) -> None:
        self.status_message.emit(f"正在扫描 {len(roots)} 个目录…")
        run_async(lambda: repo_service.upsert_repos(roots),
                  on_ok=lambda repos: (self._sync_workspace(repos),
                                       self.refresh(), self.repos_changed.emit(),
                                       self.status_message.emit(f"扫描完成：共 {len(repos)} 个仓库")),
                  on_err=lambda e: self.status_message.emit(f"扫描失败：{e}"))

    @staticmethod
    def _sync_workspace(repos) -> None:
        """把仓库列表同步进 IDE 工作区文件（失败不影响扫描结果）。"""
        try:
            workspace_service.sync_workspace(repos)
        except OSError as e:
            print(f"工作区同步失败：{e}")  # 仅控制台留痕，不打断流程

    def _fetch_all(self) -> None:
        repos = repo_service.list_repos()
        if not repos:
            QMessageBox.information(self, "fetch", "没有可 fetch 的仓库")
            return
        self.status_message.emit("正在 fetch 全部仓库（网络操作可能较慢）…")

        def work():
            ok, failed = 0, []
            for r in repos:
                try:
                    repo_service.fetch(r.path)
                    ok += 1
                except Exception as e:  # noqa: BLE001 - 单个失败不中断
                    failed.append(f"{r.name}: {e}")
            return ok, failed

        def done(result):
            ok, failed = result
            msg = f"fetch 完成：成功 {ok}/{len(repos)}"
            if failed:
                msg += "；失败：" + "；".join(failed[:3]) + ("…" if len(failed) > 3 else "")
            self.status_message.emit(msg)
            self._fill_statuses()

        run_async(work, on_ok=done, on_err=lambda e: self.status_message.emit(f"fetch 失败：{e}"))

    def _selected_repo(self) -> LocalRepo | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        repo_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return repo_service.get_repo(repo_id)

    def _detail(self) -> None:
        repo = self._selected_repo()
        if repo:
            RepoDetailDialog(repo, self).exec()

    def _menu(self, pos) -> None:
        repo = self._selected_repo()
        if repo is None:
            return
        menu = QMenu(self)
        detail = menu.addAction("查看详情")
        detail.triggered.connect(self._detail)
        explorer = menu.addAction("在资源管理器中打开")
        explorer.triggered.connect(lambda: os.startfile(repo.path))  # noqa: S606 - Windows 打开目录
        copy = menu.addAction("复制路径")
        copy.triggered.connect(lambda: QGuiApplication.clipboard().setText(repo.path))
        if repo.owner_repo:
            menu.addSeparator()
            github = menu.addAction(f"在 GitHub 面板查看（{repo.owner_repo}）")
            github.triggered.connect(lambda: self.view_on_github.emit(repo.owner_repo))
        menu.exec(self.table.viewport().mapToGlobal(pos))
