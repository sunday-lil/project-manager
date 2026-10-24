"""本地仓库管理：扫描、状态表格、详情、终端/编辑器、fetch/pull。"""
from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHeaderView,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import SETTING_SYNC_WORKSPACE, SYNC_WORKSPACE_ENABLED, WORKSPACE_FILE
from app.core import shell
from app.core.settings import SettingsStore
from app.core.workers import run_async
from app.models.repo import LocalRepo
from app.services import repo_service, workspace_service
from app.ui import theme
from app.ui.dialogs.repo_detail_dialog import RepoDetailDialog
from app.ui.widgets.common import PageHeader

_HEADERS = ["名称", "分支", "改动", "领先", "落后", "最近提交", "路径"]


class _PathDelegate(QStyledItemDelegate):
    """Windows 路径按 ElideRight 会被 Qt 截成 "C:..."，这里手动做中间省略。"""

    def paint(self, painter, option, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        elided = opt.fontMetrics.elidedText(text, Qt.TextElideMode.ElideMiddle, rect.width())
        painter.save()
        painter.setFont(opt.font)
        if opt.state & QStyle.StateFlag.State_Selected:
            painter.setPen(opt.palette.color(QPalette.ColorRole.HighlightedText))
        else:
            painter.setPen(opt.palette.color(QPalette.ColorRole.Text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         elided)
        painter.restore()


class ReposTab(QWidget):
    status_message = Signal(str)
    repos_changed = Signal()          # 仓库列表变化，通知其它页面联动刷新
    view_on_github = Signal(str)      # owner_repo，主窗口转发给 GitHub 页

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._repos: dict[int, LocalRepo] = {}
        self._row_by_id: dict[int, int] = {}
        self._load_gen = 0

        self.header = PageHeader("本地仓库", "扫描工作区里的 git 仓库，掌握每条分支的落点")
        self.scan_btn = QPushButton("＋ 添加扫描目录")
        self.scan_btn.setProperty("variant", "primary")
        self.scan_btn.clicked.connect(self._scan)
        self.header.add_action(self.scan_btn)

        self.refresh_btn = QPushButton("刷新状态")
        self.refresh_btn.clicked.connect(self.refresh)
        self.header.add_action(self.refresh_btn)

        self.fetch_btn = QPushButton("fetch 全部")
        self.fetch_btn.clicked.connect(self._fetch_all)
        self.header.add_action(self.fetch_btn)

        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(self._detail)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        widths = {0: 190, 1: 150, 2: 68, 3: 68, 4: 68, 5: 125}
        for i, width in widths.items():
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, width)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(6, _PathDelegate(self.table))

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(14)
        root.addWidget(self.header)
        root.addWidget(self.table, stretch=1)
        self.refresh()

    # ---------- 数据加载 ----------

    def refresh(self) -> None:
        repos = repo_service.list_repos()
        self._repos = {r.id: r for r in repos}
        self._row_by_id = {}
        self.table.setRowCount(len(repos))
        for i, repo in enumerate(repos):
            self._row_by_id[repo.id] = i
            name = QTableWidgetItem(repo.name or repo.path)
            name.setData(Qt.ItemDataRole.UserRole, repo.id)
            name.setToolTip("\n".join(filter(None, [
                repo.name, repo.path,
                f"GitHub：{repo.owner_repo}" if repo.owner_repo else ""])))
            self.table.setItem(i, 0, name)
            for j in range(1, len(_HEADERS)):
                self.table.setItem(i, j, QTableWidgetItem("…" if j < 6 else repo.path))
            self.table.item(i, 6).setToolTip(repo.path)
        self.header.set_subtitle(f"{len(repos)} 个仓库" if repos
                                 else "还没有仓库：添加一个扫描目录开始")
        if repos:
            self._load_statuses()

    def _load_statuses(self) -> None:
        self._load_gen += 1
        gen = self._load_gen
        self.refresh_btn.setEnabled(False)
        ids = list(self._row_by_id)

        def work():
            return repo_service.all_statuses()

        def fill(pairs):
            if gen != self._load_gen:  # 期间又发起了新的刷新，丢弃旧结果
                return
            self.refresh_btn.setEnabled(True)
            dirty = behind = ahead = 0
            for repo, st in pairs:
                row = self._row_by_id.get(repo.id)
                if row is None or row >= self.table.rowCount():
                    continue
                if st.error:
                    err = QTableWidgetItem(st.error)
                    err.setForeground(QColor(theme.tone("danger")))
                    self.table.setItem(row, 1, err)
                    for j in range(2, 6):
                        self.table.setItem(row, j, QTableWidgetItem("—"))
                    continue
                branch_item = QTableWidgetItem(st.branch)
                branch_item.setToolTip(st.branch)
                self.table.setItem(row, 1, branch_item)
                dirty_text = f"{st.dirty_count} 处" if st.is_dirty else "干净"
                dirty_item = QTableWidgetItem(dirty_text)
                if st.is_dirty:
                    dirty_item.setForeground(QColor(theme.tone("warning")))
                    dirty += 1
                self.table.setItem(row, 2, dirty_item)

                ahead_item = QTableWidgetItem(f"↑{st.ahead}" if st.ahead else "—")
                if st.ahead:
                    ahead_item.setForeground(QColor(theme.tone("accent")))
                    ahead += 1
                self.table.setItem(row, 3, ahead_item)

                behind_item = QTableWidgetItem(f"↓{st.behind}" if st.behind else "—")
                if st.behind:
                    behind_item.setForeground(QColor(theme.tone("danger")))
                    behind += 1
                self.table.setItem(row, 4, behind_item)

                commit = QTableWidgetItem(st.last_commit_at or "—")
                commit.setToolTip(st.last_commit_msg)
                self.table.setItem(row, 5, commit)
            self.header.set_subtitle(
                f"{len(pairs)} 个仓库 · {dirty} 个有改动 · {ahead} 个待推送 · {behind} 个落后")
            self.status_message.emit(f"仓库状态已刷新（{len(pairs)} 个）")

        def failed(err):
            self.refresh_btn.setEnabled(True)
            self.status_message.emit(f"刷新失败：{err}")

        if not ids:
            self.refresh_btn.setEnabled(True)
            return
        self.status_message.emit(f"正在读取 {len(ids)} 个仓库的状态…")
        run_async(work, on_ok=fill, on_err=failed)

    # ---------- 扫描 / 拉取 ----------

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
        self.scan_btn.setEnabled(False)

        def done(repos):
            self.scan_btn.setEnabled(True)
            self._sync_workspace(repos)
            self.refresh()
            self.repos_changed.emit()
            self.status_message.emit(f"扫描完成：共 {len(repos)} 个仓库")

        def failed(err):
            self.scan_btn.setEnabled(True)
            self.status_message.emit(f"扫描失败：{err}")

        run_async(lambda: repo_service.upsert_repos(roots), on_ok=done, on_err=failed)

    @staticmethod
    def _sync_workspace(repos) -> None:
        """把仓库列表同步进 IDE 工作区文件（失败不影响扫描结果）。"""
        if not SYNC_WORKSPACE_ENABLED:
            return
        if (SettingsStore.get(SETTING_SYNC_WORKSPACE) or "1") == "0":
            return
        try:
            workspace_service.sync_workspace(repos)
        except OSError as e:
            print(f"工作区同步失败（{WORKSPACE_FILE}）：{e}")

    def _fetch_all(self) -> None:
        repos = repo_service.list_repos()
        if not repos:
            QMessageBox.information(self, "fetch", "没有可 fetch 的仓库")
            return
        self.fetch_btn.setEnabled(False)
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
            self.fetch_btn.setEnabled(True)
            ok, failed = result
            msg = f"fetch 完成：成功 {ok}/{len(repos)}"
            if failed:
                msg += "；失败：" + "；".join(failed[:3]) + ("…" if len(failed) > 3 else "")
            self.status_message.emit(msg)
            self._load_statuses()

        run_async(work, on_ok=done,
                  on_err=lambda e: (self.fetch_btn.setEnabled(True),
                                    self.status_message.emit(f"fetch 失败：{e}")))

    # ---------- 选择与操作 ----------

    def _selected_repo(self) -> LocalRepo | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return self._repos.get(item.data(Qt.ItemDataRole.UserRole))

    def _detail(self) -> None:
        repo = self._selected_repo()
        if repo:
            RepoDetailDialog(repo, self).exec()

    def _pull(self, repo: LocalRepo) -> None:
        self.status_message.emit(f"正在拉取 {repo.name} …")

        def done(msg):
            self.status_message.emit(f"{repo.name}：{msg}")
            self._load_statuses()

        run_async(lambda: repo_service.pull(repo.path), on_ok=done,
                  on_err=lambda e: self.status_message.emit(f"{repo.name}：{e}"))

    def _open_terminal(self, repo: LocalRepo) -> None:
        try:
            shell.open_terminal(repo.path)
        except OSError as e:
            self.status_message.emit(f"无法打开终端：{e}")

    def _open_vscode(self, repo: LocalRepo) -> None:
        try:
            shell.open_vscode(repo.path)
        except (OSError, RuntimeError) as e:
            self.status_message.emit(str(e))

    def _menu(self, pos) -> None:
        repo = self._selected_repo()
        if repo is None:
            return
        menu = QMenu(self)
        menu.addAction("查看详情").triggered.connect(self._detail)
        menu.addAction("在资源管理器中打开").triggered.connect(
            lambda: shell.open_in_explorer(repo.path))
        menu.addAction("在终端中打开").triggered.connect(lambda: self._open_terminal(repo))
        menu.addAction("在 VS Code 中打开").triggered.connect(lambda: self._open_vscode(repo))
        menu.addSeparator()
        menu.addAction("拉取更新（--ff-only）").triggered.connect(lambda: self._pull(repo))
        menu.addAction("复制路径").triggered.connect(
            lambda: QGuiApplication.clipboard().setText(repo.path))
        if repo.owner_repo:
            menu.addSeparator()
            menu.addAction(f"在 GitHub 页查看（{repo.owner_repo}）").triggered.connect(
                lambda: self.view_on_github.emit(repo.owner_repo))
        menu.exec(self.table.viewport().mapToGlobal(pos))
