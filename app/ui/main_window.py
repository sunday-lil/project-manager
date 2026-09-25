"""主窗口：三 Tab + 菜单栏 + 状态栏，跨 Tab 信号路由。"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget

from app.constants import APP_NAME
from app.core.settings import get_github_token
from app.services import repo_service, workspace_service
from app.services.github_service import GithubService
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.tabs.github_tab import GithubTab
from app.ui.tabs.kanban_tab import KanbanTab
from app.ui.tabs.repos_tab import ReposTab


class GithubContext:
    """GitHub 服务上下文：持有 token，设置变更后统一刷新。"""

    def __init__(self):
        self.reload_token()

    def reload_token(self) -> None:
        self.token = get_github_token()

    def service(self) -> GithubService:
        return GithubService(self.token)

    def has_token(self) -> bool:
        return bool(self.token)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1150, 720)

        self.ctx = GithubContext()
        self._status_stamp = 0
        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label)

        self.kanban_tab = KanbanTab(self.ctx)
        self.repos_tab = ReposTab()
        self.github_tab = GithubTab(self.ctx)
        for tab in (self.kanban_tab, self.repos_tab, self.github_tab):
            tab.status_message.connect(self.show_status)
        self.repos_tab.view_on_github.connect(self._jump_to_github)
        self.repos_tab.repos_changed.connect(self.kanban_tab.refresh_repos)

        tabs = QTabWidget()
        tabs.addTab(self.kanban_tab, "任务看板")
        tabs.addTab(self.repos_tab, "本地仓库")
        tabs.addTab(self.github_tab, "GitHub")
        tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(tabs)

        menu = self.menuBar().addMenu("工具")
        menu.addAction("设置…").triggered.connect(self._open_settings)

        self.kanban_tab.refresh_repos()
        self._sync_workspace_on_start()

    def _sync_workspace_on_start(self) -> None:
        """启动时把当前仓库列表同步进 IDE 工作区文件（增删改全覆盖）。"""
        try:
            workspace_service.sync_workspace(repo_service.list_repos())
        except OSError as e:
            print(f"工作区同步失败：{e}")  # 仅控制台留痕，不打断启动

    # ---------- 信号路由 ----------

    def _on_tab_changed(self, index: int) -> None:
        if index == 0:  # 仓库扫描可能在本地仓库 Tab 更新过
            self.kanban_tab.refresh_repos()

    def _jump_to_github(self, owner_repo: str) -> None:
        self.centralWidget().setCurrentIndex(2)
        self.github_tab.load_repo(owner_repo)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self) -> None:
        self.ctx.reload_token()
        self.show_status("设置已保存")
        self.repos_tab.rescan()  # 根目录或 Token 可能变了，重新扫描刷新仓库列表

    def show_status(self, msg: str) -> None:
        """状态栏提示 6 秒后自动恢复（仅最新一条生效）。"""
        self.status_label.setText(msg)
        self._status_stamp += 1
        stamp = self._status_stamp
        QTimer.singleShot(6000, lambda: self._clear_status(stamp))

    def _clear_status(self, stamp: int) -> None:
        if stamp == self._status_stamp:
            self.status_label.setText("就绪")
