"""主窗口：侧边栏导航 + 页面栈 + 菜单/快捷键 + 状态栏。"""
import os
from datetime import date
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    DATA_DIR,
    LOG_PATH,
    SETTING_SYNC_WORKSPACE,
    SYNC_WORKSPACE_ENABLED,
    THEME_LABELS,
    THEMES,
)
from app.core.backup import backup_db
from app.core.settings import (
    SettingsStore,
    get_github_token,
    get_last_page,
    get_theme,
    set_last_page,
    set_theme,
)
from app.services import export_service, repo_service, workspace_service
from app.services.github_service import GithubService
from app.ui import theme
from app.ui.brand import app_icon
from app.ui.dialogs.about_dialog import AboutDialog
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.tabs.dashboard_tab import DashboardTab
from app.ui.tabs.github_tab import GithubTab
from app.ui.tabs.kanban_tab import KanbanTab
from app.ui.tabs.repos_tab import ReposTab

_NAV = (
    ("dashboard", "◈", "工作台"),
    ("kanban", "▤", "任务看板"),
    ("repos", "⌂", "本地仓库"),
    ("github", "◎", "GitHub"),
)


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
        self.setWindowTitle(f"{APP_NAME} · v{APP_VERSION}")
        self.setMinimumSize(1020, 660)
        self.resize(1280, 800)
        self.setWindowIcon(app_icon())

        self.ctx = GithubContext()
        self._dashboard_dirty = False
        self._status_stamp = 0
        self._nav_keys = [k for k, _, _ in _NAV]

        self._build_status_bar()
        self._build_central()
        self._build_menu()
        self._build_shortcuts()
        self._wire()

        self._restore_geometry()
        self._update_token_badge()
        self._sync_workspace_on_start()

        last = get_last_page()
        self._navigate(last if last in self._nav_keys else "dashboard", force=False)
        self.show_status("就绪 · 双击卡片编辑，拖拽卡片改变状态")

    # ---------- 构建 ----------

    def _build_status_bar(self) -> None:
        self.status_label = QLabel("就绪")
        self.status_label.setMinimumWidth(360)
        self.token_status = QLabel("")
        self.version_label = QLabel(f"v{APP_VERSION}")
        bar = self.statusBar()
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.token_status)
        bar.addPermanentWidget(self.version_label)
        self.token_status.setToolTip(f"数据目录：{DATA_DIR}")

    def _build_central(self) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(216)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(6)

        self.brand_icon = QLabel()
        self.brand_icon.setPixmap(app_icon(38).pixmap(38, 38))
        name = QLabel(APP_NAME)
        name.setProperty("role", "brand")
        tag = QLabel(APP_TAGLINE)
        tag.setProperty("role", "brandSub")
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(name)
        brand_text.addWidget(tag)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(self.brand_icon)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(14)

        section = QLabel("工作区")
        section.setProperty("role", "navSection")
        side.addWidget(section)

        self.nav_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, glyph, label in _NAV:
            btn = QPushButton(f"{glyph}   {label}")
            btn.setProperty("nav", "true")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _=False, k=key: self._navigate(k))
            group.addButton(btn)
            side.addWidget(btn)
            self.nav_buttons[key] = btn

        side.addStretch(1)

        divider = QFrame()
        divider.setProperty("role", "hline")
        side.addWidget(divider)
        side.addSpacing(6)

        settings_btn = QPushButton("⚙   设置")
        settings_btn.setProperty("nav", "true")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setMinimumHeight(36)
        settings_btn.clicked.connect(self._open_settings)
        side.addWidget(settings_btn)

        self.side_token = QLabel("")
        self.side_token.setProperty("role", "chip")
        self.side_version = QLabel(f"v{APP_VERSION} · MIT")
        self.side_version.setProperty("role", "faint")
        foot = QHBoxLayout()
        foot.setContentsMargins(4, 6, 0, 0)
        foot.addWidget(self.side_token)
        foot.addStretch(1)
        foot.addWidget(self.side_version)
        side.addLayout(foot)

        self.dashboard_tab = DashboardTab()
        self.kanban_tab = KanbanTab(self.ctx)
        self.repos_tab = ReposTab()
        self.github_tab = GithubTab(self.ctx)
        self.page_by_key = {
            "dashboard": self.dashboard_tab,
            "kanban": self.kanban_tab,
            "repos": self.repos_tab,
            "github": self.github_tab,
        }

        self.stack = QStackedWidget()
        self.stack.setObjectName("pages")
        for key in self._nav_keys:
            self.stack.addWidget(self.page_by_key[key])

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("文件")
        self._add_action(file_menu, "导出任务 CSV…", self._export_csv, "Ctrl+E")
        self._add_action(file_menu, "备份数据库", self._backup_now)
        self._add_action(file_menu, "打开数据目录", lambda: os.startfile(DATA_DIR))
        file_menu.addSeparator()
        self._add_action(file_menu, "退出", self.close, "Ctrl+Q")

        view_menu = bar.addMenu("视图")
        self._add_action(view_menu, "刷新当前页", self._refresh_current, "F5")
        theme_menu = view_menu.addMenu("主题")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions: dict[str, QAction] = {}
        for key in THEMES:
            act = QAction(THEME_LABELS[key], self)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, k=key: self._set_theme(k))
            self.theme_group.addAction(act)
            theme_menu.addAction(act)
            self.theme_actions[key] = act
        self._check_theme()

        tools_menu = bar.addMenu("工具")
        self._add_action(tools_menu, "设置…", self._open_settings, "Ctrl+,")
        self._add_action(tools_menu, "打开日志文件", self._open_log)

        help_menu = bar.addMenu("帮助")
        self._add_action(help_menu, f"关于 {APP_NAME}", self._about)

    @staticmethod
    def _add_action(menu, text: str, slot, shortcut: str | None = None) -> QAction:
        act = QAction(text, menu)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _build_shortcuts(self) -> None:
        self._shortcuts: list[QShortcut] = []
        for i, key in enumerate(self._nav_keys, start=1):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda k=key: self._navigate(k))
            self._shortcuts.append(sc)
        for seq, slot in (("Ctrl+N", self._new_task_shortcut),
                          ("Ctrl+K", self._focus_search)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

    def _wire(self) -> None:
        for page in self.page_by_key.values():
            page.status_message.connect(self.show_status)
        self.dashboard_tab.new_task_requested.connect(self._new_task_shortcut)
        self.dashboard_tab.open_kanban.connect(lambda: self._navigate("kanban"))
        self.dashboard_tab.open_repos.connect(lambda: self._navigate("repos"))
        self.dashboard_tab.task_activated.connect(self._open_task)
        self.kanban_tab.tasks_changed.connect(self._on_tasks_changed)
        self.repos_tab.repos_changed.connect(self._on_repos_changed)
        self.repos_tab.view_on_github.connect(self._jump_to_github)

    # ---------- 导航 ----------

    def _navigate(self, key: str, force: bool = True) -> None:
        if key not in self.page_by_key:
            key = "dashboard"
        index = self._nav_keys.index(key)
        self.stack.setCurrentIndex(index)
        self.nav_buttons[key].setChecked(True)
        set_last_page(key)
        if key == "dashboard" and (force or self._dashboard_dirty):
            self.dashboard_tab.refresh()
            self._dashboard_dirty = False
        elif key == "kanban":
            self.kanban_tab.reload()
        elif key == "github":
            self.github_tab.repo_box.setFocus()

    def _jump_to_github(self, owner_repo: str) -> None:
        self._navigate("github")
        self.github_tab.load_repo(owner_repo)

    def _open_task(self, task_id: int) -> None:
        self._navigate("kanban")
        self.kanban_tab.edit_task(task_id)

    def _new_task_shortcut(self) -> None:
        self._navigate("kanban")
        self.kanban_tab.new_task()

    def _focus_search(self) -> None:
        self._navigate("kanban")
        self.kanban_tab.focus_search()

    def _on_tasks_changed(self) -> None:
        if self._nav_keys[self.stack.currentIndex()] == "dashboard":
            self.dashboard_tab.refresh()
        else:
            self._dashboard_dirty = True

    def _on_repos_changed(self) -> None:
        self.kanban_tab.refresh_repos()
        self.github_tab.refresh_repos()
        if self._nav_keys[self.stack.currentIndex()] == "dashboard":
            self.dashboard_tab.refresh()
        else:
            self._dashboard_dirty = True

    # ---------- 设置 / 主题 ----------

    def _open_settings(self) -> None:
        before_roots = SettingsStore.get_scan_roots()
        before_theme = get_theme()
        dlg = SettingsDialog(self)
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return

        self.ctx.reload_token()
        self._update_token_badge()
        self.github_tab.refresh_token_state()
        if get_theme() != before_theme:
            self._apply_theme(get_theme(), notify=False)
        self.kanban_tab.reload()
        self.dashboard_tab.refresh()
        if SettingsStore.get_scan_roots() != before_roots:
            self.repos_tab.rescan()
        self.show_status("设置已保存")

    def _set_theme(self, mode: str) -> None:
        set_theme(mode)
        self._apply_theme(mode, notify=True)

    def _apply_theme(self, mode: str, notify: bool = True) -> None:
        theme.apply(QApplication.instance(), mode)
        self.setWindowIcon(app_icon())
        self.brand_icon.setPixmap(app_icon(38).pixmap(38, 38))
        self._check_theme()
        self.repos_tab.refresh()
        self.kanban_tab.reload()
        self.github_tab.restyle()
        self.dashboard_tab.refresh()
        if notify:
            self.show_status(f"主题已切换：{THEME_LABELS.get(mode, mode)}")

    def _check_theme(self) -> None:
        current = get_theme()
        for key, act in self.theme_actions.items():
            act.setChecked(key == current)

    # ---------- 状态 ----------

    def _update_token_badge(self) -> None:
        if self.ctx.has_token():
            text, tone = "GitHub 已连接", "success"
        else:
            text, tone = "GitHub 匿名只读", "warning"
        for label in (self.side_token, self.token_status):
            label.setText(text)
            label.setProperty("tone", tone)
            theme.repolish(label)

    def show_status(self, msg: str) -> None:
        """状态栏提示 6 秒后自动恢复（仅最新一条生效）。"""
        self.status_label.setText(msg)
        self._status_stamp += 1
        stamp = self._status_stamp
        QTimer.singleShot(6000, lambda: self._clear_status(stamp))

    def _clear_status(self, stamp: int) -> None:
        if stamp == self._status_stamp:
            self.status_label.setText("就绪")

    def _refresh_current(self) -> None:
        key = self._nav_keys[self.stack.currentIndex()]
        if key == "dashboard":
            self.dashboard_tab.refresh()
        elif key == "kanban":
            self.kanban_tab.reload()
        elif key == "repos":
            self.repos_tab.refresh()
        elif key == "github":
            if self.github_tab.current_repo:
                self.github_tab.load()
        self.show_status("已刷新")

    # ---------- 菜单动作 ----------

    def _export_csv(self) -> None:
        default = str(Path.home() / "Desktop" / f"tasks-{date.today().isoformat()}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "导出任务", default, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            count = export_service.export_tasks_csv(path)
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self.show_status(f"已导出 {count} 个任务：{path}")

    def _backup_now(self) -> None:
        target = backup_db(force=True)
        if target is None:
            QMessageBox.information(self, "备份数据库", "数据库不存在或备份失败")
        else:
            self.show_status(f"已备份到：{target}")

    def _open_log(self) -> None:
        if not LOG_PATH.exists():
            QMessageBox.information(self, "日志", "日志文件尚未创建")
            return
        os.startfile(LOG_PATH)

    def _about(self) -> None:
        AboutDialog(self).exec()

    def _sync_workspace_on_start(self) -> None:
        """启动时把当前仓库列表同步进 IDE 工作区文件（可关闭）。"""
        if not SYNC_WORKSPACE_ENABLED:
            return
        if (SettingsStore.get(SETTING_SYNC_WORKSPACE) or "1") == "0":
            return
        try:
            workspace_service.sync_workspace(repo_service.list_repos())
        except OSError as e:
            print(f"工作区同步失败（{workspace_service.WORKSPACE_FILE}）：{e}")

    # ---------- 窗口状态 ----------

    def _restore_geometry(self) -> None:
        saved = SettingsStore.get("window_geometry")
        if saved:
            try:
                self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii")))
            except (ValueError, UnicodeEncodeError):
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            SettingsStore.set("window_geometry",
                              bytes(self.saveGeometry().toBase64()).decode("ascii"))
        except (OSError, ValueError):
            pass
        super().closeEvent(event)
