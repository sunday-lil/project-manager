"""设置：Token 安全存储、外观、扫描目录、合并方式。"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    MERGE_METHOD_LABELS,
    MERGE_METHODS,
    SETTING_MERGE_METHOD,
    SETTING_SYNC_WORKSPACE,
    THEME_LABELS,
    THEMES,
    WORKSPACE_FILE,
)
from app.core.settings import (
    SettingsStore,
    clear_github_token,
    get_theme,
    set_github_token,
    set_theme,
    token_status,
)


class SettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(620)
        self.resize(660, 720)
        self._clear_token = False

        title = QLabel("设置")
        title.setProperty("role", "h1")
        subtitle = QLabel("Token 只保存在本机，不会上传到任何地方")
        subtitle.setProperty("role", "subtitle")

        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setContentsMargins(24, 20, 24, 8)
        inner.setSpacing(14)
        inner.addWidget(title)
        inner.addWidget(subtitle)
        inner.addWidget(self._build_token_card())
        inner.addWidget(self._build_appearance_card())
        inner.addWidget(self._build_roots_card())
        inner.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setProperty("variant", "primary")
        save.clicked.connect(self._save)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(24, 0, 24, 16)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(scroll, stretch=1)
        root.addLayout(buttons)

    # ---------- 区块 ----------

    @staticmethod
    def _section(title: str) -> QLabel:
        label = QLabel(title)
        label.setProperty("role", "section")
        return label

    def _build_token_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(self._section("GitHub 访问"))
        self.token_state = QLabel("")
        self.token_state.setProperty("role", "chip")
        head.addWidget(self.token_state)
        head.addStretch(1)
        layout.addLayout(head)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.textChanged.connect(self._on_token_typed)
        show_btn = QCheckBox("显示")
        show_btn.toggled.connect(
            lambda on: self.token_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        clear_btn = QPushButton("清除")
        clear_btn.setProperty("variant", "ghost")
        clear_btn.clicked.connect(self._clear)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.token_edit, stretch=1)
        row.addWidget(show_btn)
        row.addWidget(clear_btn)
        layout.addLayout(row)

        tip = QLabel("建议使用 fine-grained token：仅勾选需要管理的仓库，权限选 Metadata(读)、"
                     "Issues(读写)、Pull requests(读写)、Contents(读写)。保存后离开本机也不会泄露明文。")
        tip.setWordWrap(True)
        tip.setProperty("role", "faint")
        layout.addWidget(tip)

        self._refresh_token_state()
        return card

    def _build_appearance_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(self._section("外观与行为"))

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("主题"))
        self.theme_box = QComboBox()
        for key in THEMES:
            self.theme_box.addItem(THEME_LABELS[key], key)
        idx = self.theme_box.findData(get_theme())
        self.theme_box.setCurrentIndex(idx if idx >= 0 else 0)
        theme_row.addWidget(self.theme_box, stretch=1)
        layout.addLayout(theme_row)

        merge_row = QHBoxLayout()
        merge_row.addWidget(QLabel("默认合并方式"))
        self.merge_box = QComboBox()
        for m in MERGE_METHODS:
            self.merge_box.addItem(MERGE_METHOD_LABELS[m], m)
        saved = SettingsStore.get(SETTING_MERGE_METHOD)
        if saved in MERGE_METHODS:
            self.merge_box.setCurrentIndex(MERGE_METHODS.index(saved))
        merge_row.addWidget(self.merge_box, stretch=1)
        layout.addLayout(merge_row)

        self.sync_workspace = QCheckBox("扫描仓库后同步 IDE 多根工作区文件")
        self.sync_workspace.setChecked((SettingsStore.get(SETTING_SYNC_WORKSPACE) or "1") != "0")
        self.sync_workspace.setToolTip(str(WORKSPACE_FILE))
        layout.addWidget(self.sync_workspace)
        return card

    def _build_roots_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._section("仓库扫描目录"))

        self.roots_list = QListWidget()
        self.roots_list.setProperty("role", "insetList")
        self.roots_list.setFixedHeight(128)
        for root in SettingsStore.get_scan_roots():
            self.roots_list.addItem(QListWidgetItem(root))
        layout.addWidget(self.roots_list)

        add = QPushButton("添加目录…")
        add.setProperty("variant", "ghost")
        add.clicked.connect(self._add_root)
        remove = QPushButton("移除选中")
        remove.setProperty("variant", "ghost")
        remove.clicked.connect(self._remove_root)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)

        tip = QLabel("扫描会递归 3 层，遇到 .git 即停止；磁盘上已删除的仓库会自动清理。")
        tip.setProperty("role", "faint")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        return card

    # ---------- Token 状态 ----------

    def _refresh_token_state(self) -> None:
        status = token_status()
        if self._clear_token:
            self.token_state.setText("保存后清除")
            self.token_state.setProperty("tone", "danger")
            self.token_edit.setPlaceholderText("清除后需要重新填写")
        elif status["configured"] and status["encrypted"]:
            self.token_state.setText("已加密保存")
            self.token_state.setProperty("tone", "success")
            self.token_edit.setPlaceholderText("已配置（留空保持不变）")
        elif status["configured"]:
            self.token_state.setText("已保存（明文）")
            self.token_state.setProperty("tone", "warning")
            self.token_edit.setPlaceholderText("已配置（留空保持不变）")
        else:
            self.token_state.setText("未配置")
            self.token_state.setProperty("tone", "warning")
            self.token_edit.setPlaceholderText("ghp_… 或 github_pat_…")
        self.token_state.style().unpolish(self.token_state)
        self.token_state.style().polish(self.token_state)

    def _on_token_typed(self, text: str) -> None:
        if text and self._clear_token:
            self._clear_token = False
            self._refresh_token_state()

    def _clear(self) -> None:
        self._clear_token = True
        self.token_edit.clear()
        self._refresh_token_state()

    # ---------- 扫描目录 ----------

    def _add_root(self) -> None:
        start = self.roots_list.item(self.roots_list.count() - 1)
        path = QFileDialog.getExistingDirectory(
            self, "添加扫描根目录", start.text() if start else "")
        if not path:
            return
        existing = {self.roots_list.item(i).text() for i in range(self.roots_list.count())}
        if path not in existing:
            self.roots_list.addItem(QListWidgetItem(path))

    def _remove_root(self) -> None:
        row = self.roots_list.currentRow()
        if row >= 0:
            self.roots_list.takeItem(row)

    # ---------- 保存 ----------

    def _roots(self) -> list[str]:
        return [self.roots_list.item(i).text() for i in range(self.roots_list.count())]

    def _save(self) -> None:
        typed = self.token_edit.text().strip()
        if self._clear_token:
            clear_github_token()
        elif typed:
            set_github_token(typed)
        # 留空且未点清除：保持原 Token 不动
        set_theme(self.theme_box.currentData())
        SettingsStore.set(SETTING_SYNC_WORKSPACE, "1" if self.sync_workspace.isChecked() else "0")
        SettingsStore.set(SETTING_MERGE_METHOD, self.merge_box.currentData())
        SettingsStore.set_scan_roots(self._roots())
        self.settings_saved.emit()
        self.accept()
