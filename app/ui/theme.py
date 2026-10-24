"""视觉主题：设计令牌 + 全局 QSS + 调色板。

所有颜色/圆角/字号集中在这里。控件通过 objectName / 动态属性取样式，
这样切换主题时只需重设 QSS，无需重建界面。
"""
from pathlib import Path
from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from app.constants import DATA_DIR

FONT_FAMILY = '"Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif'

LIGHT = {
    "bg": "#F3F5F9",
    "sidebar": "#FFFFFF",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "surface_soft": "#EEF2F7",
    "border": "#E4E9F0",
    "border_strong": "#CBD5E1",
    "text": "#16202E",
    "muted": "#5B6B7F",
    "faint": "#93A1B5",
    "accent": "#3B63E0",
    "accent_hover": "#2F53C7",
    "accent_soft": "#E9EFFD",
    "success": "#12805C",
    "success_soft": "#E4F6EE",
    "warning": "#B26A00",
    "warning_soft": "#FDF1DE",
    "danger": "#D14343",
    "danger_soft": "#FCE9E9",
    "is_dark": False,
}

DARK = {
    "bg": "#0E1217",
    "sidebar": "#0A0D11",
    "surface": "#171C23",
    "surface_alt": "#1D242C",
    "surface_soft": "#232B35",
    "border": "#2A3340",
    "border_strong": "#3A4658",
    "text": "#E8EDF5",
    "muted": "#9AA8BC",
    "faint": "#6C7A8E",
    "accent": "#7C9BFF",
    "accent_hover": "#9AB2FF",
    "accent_soft": "#1E2942",
    "success": "#46D39A",
    "success_soft": "#123026",
    "warning": "#F0B45C",
    "warning_soft": "#322612",
    "danger": "#F07A7A",
    "danger_soft": "#351B1F",
    "is_dark": True,
}

_current_mode = "light"


def resolve_mode(setting: str = "system") -> str:
    """把设置值解析成 light/dark；system 时读取 Windows 应用主题。"""
    if setting in ("light", "dark"):
        return setting
    app = QApplication.instance()
    if app is not None:
        try:
            if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
                return "dark"
        except AttributeError:  # Qt < 6.5
            pass
    return "light"


def mode() -> str:
    return _current_mode


def tokens() -> dict:
    return DARK if _current_mode == "dark" else LIGHT


def tone(name: str) -> str:
    """语义色 → 十六进制，供自绘控件使用。"""
    return tokens().get(name, tokens()["text"])


def repolish(widget) -> None:
    """动态属性变化后重新套用 QSS。"""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def apply(app: QApplication, setting: str = "system") -> str:
    """应用主题，返回实际使用的 light/dark。"""
    global _current_mode
    _current_mode = resolve_mode(setting)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setPalette(_palette(tokens()))
    chevron = _chevron_icon(tokens()["muted"], _current_mode)
    app.setStyleSheet(_qss(tokens(), _check_icon(), chevron))
    return _current_mode


def _chevron_icon(color: str, suffix: str) -> str:
    """下拉框箭头（不依赖外部资源）。"""
    path = Path(DATA_DIR) / f"chevron_{suffix}.png"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pm = QPixmap(12, 8)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(2.5, 2.5), QPointF(6.0, 6.0), QPointF(9.5, 2.5)])
        p.end()
        pm.save(str(path))
    except OSError:
        return ""
    return path.as_posix()


def _check_icon() -> str:
    """生成勾选图标（QSS 需要文件路径），QSS 的 image 不会缩放内置图形。"""
    path = Path(DATA_DIR) / "check.png"
    if path.exists():
        return path.as_posix()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#FFFFFF"))
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(3.5, 8.5), QPointF(6.5, 11.5), QPointF(12.5, 4.5)])
        p.end()
        pm.save(str(path))
    except OSError:
        return ""
    return path.as_posix()


def _palette(t: dict) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["bg"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["surface"],
        QPalette.ColorRole.AlternateBase: t["surface_alt"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.Button: t["surface"],
        QPalette.ColorRole.ButtonText: t["text"],
        QPalette.ColorRole.BrightText: t["danger"],
        QPalette.ColorRole.Highlight: t["accent"],
        QPalette.ColorRole.HighlightedText: "#FFFFFF" if not t["is_dark"] else "#0B0E12",
        QPalette.ColorRole.ToolTipBase: t["text"],
        QPalette.ColorRole.ToolTipText: t["surface"] if not t["is_dark"] else t["bg"],
        QPalette.ColorRole.PlaceholderText: t["faint"],
        QPalette.ColorRole.Mid: t["border_strong"],
        QPalette.ColorRole.Dark: t["border_strong"],
        QPalette.ColorRole.Light: t["surface"],
        QPalette.ColorRole.Link: t["accent"],
        QPalette.ColorRole.LinkVisited: t["accent_hover"],
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    return p


_QSS = Template("""
* {
    font-family: $font_family;
    font-size: 13px;
}
QWidget { color: $text; }
QMainWindow, QDialog { background: $bg; }
QStackedWidget#pages { background: $bg; }
QWidget#page { background: $bg; }

/* ---------- 侧边栏 ---------- */
QFrame#sidebar { background: $sidebar; border-right: 1px solid $border; }
QLabel[role="brand"] { font-size: 17px; font-weight: 700; color: $text; }
QLabel[role="brandSub"] { font-size: 10px; color: $faint; }
QLabel[role="navSection"] { font-size: 10px; color: $faint; padding-left: 12px; }
QPushButton[nav="true"] {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 8px;
    padding: 9px 12px 9px 13px;
    text-align: left;
    color: $muted;
    font-size: 13px;
}
QPushButton[nav="true"]:hover { background: $surface_alt; color: $text; }
QPushButton[nav="true"]:checked {
    background: $accent_soft;
    border-left: 3px solid $accent;
    color: $accent;
    font-weight: 600;
}
QFrame[role="sidebarFoot"] { border-top: 1px solid $border; }

/* ---------- 文本角色 ---------- */
QLabel[role="h1"] { font-size: 22px; font-weight: 700; color: $text; }
QLabel[role="h2"] { font-size: 15px; font-weight: 600; color: $text; }
QLabel[role="section"] { font-size: 12px; font-weight: 600; color: $muted; }
QLabel[role="subtitle"] { font-size: 12px; color: $muted; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="faint"] { color: $faint; font-size: 11px; }
QLabel[role="stat"] { font-size: 30px; font-weight: 700; color: $text; }
QLabel[role="stat"][tone="accent"] { color: $accent; }
QLabel[role="stat"][tone="warning"] { color: $warning; }
QLabel[role="stat"][tone="danger"] { color: $danger; }
QLabel[role="stat"][tone="success"] { color: $success; }
QLabel[role="statLabel"] { font-size: 12px; color: $muted; }
QLabel[role="empty"] { color: $faint; font-size: 12px; }
QLabel[role="chip"] {
    background: $surface_soft;
    color: $muted;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 11px;
}
QLabel[role="chip"][tone="accent"] { background: $accent_soft; color: $accent; }
QLabel[role="chip"][tone="success"] { background: $success_soft; color: $success; }
QLabel[role="chip"][tone="warning"] { background: $warning_soft; color: $warning; }
QLabel[role="chip"][tone="danger"] { background: $danger_soft; color: $danger; }

/* ---------- 容器 ---------- */
QFrame[role="card"], QFrame[role="panel"], QFrame[role="statCard"] {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame[role="statCard"][tone="accent"] { border-top: 3px solid $accent; }
QFrame[role="statCard"][tone="warning"] { border-top: 3px solid $warning; }
QFrame[role="statCard"][tone="danger"] { border-top: 3px solid $danger; }
QFrame[role="statCard"][tone="success"] { border-top: 3px solid $success; }
QFrame[role="column"] {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 14px;
}
QFrame[role="hline"] { background: $border; max-height: 1px; min-height: 1px; border: none; }
QFrame[role="row"] {
    background: transparent;
    border: none;
    border-bottom: 1px solid $border;
    border-radius: 6px;
}
QFrame[role="row"]:hover { background: $surface_alt; }
QFrame[role="inset"] {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 10px;
}
QLabel[role="rowTitle"] { font-weight: 600; font-size: 13px; }

/* ---------- 按钮 ---------- */
QPushButton {
    background: $surface;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 7px;
    padding: 6px 12px;
}
QPushButton:hover { background: $surface_alt; border-color: $accent; }
QPushButton:pressed { background: $accent_soft; }
QPushButton:disabled { color: $faint; border-color: $border; background: $surface_alt; }
QPushButton[variant="primary"] {
    background: $accent; color: #FFFFFF; border-color: $accent; font-weight: 600;
}
QPushButton[variant="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[variant="primary"]:disabled { background: $border; border-color: $border; color: $faint; }
QPushButton[variant="ghost"] {
    background: transparent; border-color: transparent; color: $muted;
}
QPushButton[variant="ghost"]:hover { background: $surface_soft; color: $text; }
QPushButton[variant="danger"] {
    background: $danger_soft; color: $danger; border-color: transparent;
}
QPushButton[variant="danger"]:hover { border-color: $danger; }
QPushButton[variant="link"] {
    background: transparent; border: none; color: $accent; padding: 2px 4px;
}
QPushButton[variant="link"]:hover { color: $accent_hover; }
QToolButton {
    background: transparent; border: none; border-radius: 6px;
    padding: 3px 7px; color: $muted;
}
QToolButton:hover { background: $surface_soft; color: $text; }

/* ---------- 输入控件 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit, QComboBox {
    background: $surface;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 7px;
    padding: 6px 9px;
    selection-background-color: $accent;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDateEdit:focus, QComboBox:focus { border-color: $accent; }
QLineEdit:disabled, QComboBox:disabled { color: $faint; background: $surface_alt; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url("$chevron_icon"); width: 10px; height: 7px; }
QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: $accent_soft;
    selection-color: $text;
    outline: none;
}
QComboBox QAbstractItemView::item { padding: 5px 8px; border-radius: 5px; }
QDateEdit::drop-down { border: none; width: 20px; }
QDateEdit::down-arrow { image: url("$chevron_icon"); width: 10px; height: 7px; }

/* ---------- 表格 ---------- */
QTableWidget {
    background: $surface;
    alternate-background-color: $surface_alt;
    border: 1px solid $border;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: $accent_soft;
    selection-color: $text;
}
QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid $border; }
QTableWidget::item:selected { background: $accent_soft; color: $text; }
QHeaderView::section {
    background: $surface_alt;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 8px 8px;
    font-size: 12px;
    font-weight: 600;
}

/* ---------- 列表 / 滚动条 ---------- */
QListWidget { background: transparent; border: none; outline: none; }
QListWidget[role="insetList"] {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
}
QListWidget[role="insetList"]::item { padding: 5px 6px; border-radius: 5px; }
QListWidget[role="insetList"]::item:selected { background: $accent_soft; color: $text; }
QListWidget::item { background: transparent; border: none; }
QListWidget::item:selected { background: transparent; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border_strong; min-height: 26px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border_strong; min-width: 26px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---------- 任务卡片 ---------- */
QFrame#taskCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: 9px;
}
QFrame#taskCard:hover { border-color: $accent; }
QFrame#taskCard[prio="high"] { border-left: 3px solid $danger; }
QFrame#taskCard[prio="medium"] { border-left: 3px solid $warning; }
QFrame#taskCard[prio="low"] { border-left: 3px solid $success; }
QFrame#taskCard[selected="true"] { border-color: $accent; background: $accent_soft; }
QLabel#cardTitle[done="true"] { color: $muted; }

/* ---------- 内层 Tab ---------- */
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent;
    color: $muted;
    padding: 7px 14px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected { color: $accent; border-bottom: 2px solid $accent; font-weight: 600; }

/* ---------- 菜单 / 状态栏 ---------- */
QMenuBar { background: $surface; border-bottom: 1px solid $border; }
QMenuBar::item { background: transparent; padding: 5px 10px; border-radius: 5px; }
QMenuBar::item:selected { background: $accent_soft; color: $accent; }
QMenu { background: $surface; border: 1px solid $border; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 6px 26px 6px 12px; border-radius: 5px; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QStatusBar { background: $surface; border-top: 1px solid $border; color: $muted; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $muted; font-size: 11px; }
QStatusBar QLabel[tone="success"] { color: $success; }
QStatusBar QLabel[tone="warning"] { color: $warning; }
QStatusBar QLabel[tone="danger"] { color: $danger; }
QToolTip {
    background: $text; color: $bg; border: none; padding: 5px 8px; border-radius: 5px;
}

/* ---------- 其它 ---------- */
QCheckBox { spacing: 7px; color: $text; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid $border_strong;
    border-radius: 4px;
    background: $surface;
}
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked {
    background: $accent;
    border-color: $accent;
    image: url("$check_icon");
}
QDialogButtonBox QPushButton { min-width: 76px; }
QSplitter::handle { background: $border; }
""")

def _qss(t: dict, check_icon: str = "", chevron_icon: str = "") -> str:
    return _QSS.substitute(font_family=FONT_FAMILY, check_icon=check_icon,
                           chevron_icon=chevron_icon, **t)
