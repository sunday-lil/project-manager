"""通用页面组件：页头、统计卡、迷你柱状图。"""
from datetime import date

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui import theme


class PageHeader(QWidget):
    """标题 + 副标题 + 右侧操作区。"""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.title = QLabel(title)
        self.title.setProperty("role", "h1")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setProperty("role", "subtitle")

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addLayout(text)
        row.addStretch(1)
        row.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)


class StatCard(QFrame):
    """一个数字 + 说明；顶部语义色条。"""

    def __init__(self, label: str, value: int = 0, tone: str = "accent", hint: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("role", "statCard")
        self.setProperty("tone", tone)
        self._value = QLabel(str(value))
        self._value.setProperty("role", "stat")
        self._value.setProperty("tone", tone)
        self._label = QLabel(label)
        self._label.setProperty("role", "statLabel")
        self._hint = QLabel(hint)
        self._hint.setProperty("role", "faint")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        layout.addWidget(self._label)
        layout.addWidget(self._value)
        layout.addWidget(self._hint)

    def set_value(self, value: int, hint: str | None = None) -> None:
        self._value.setText(str(value))
        if hint is not None:
            self._hint.setText(hint)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        self._value.setProperty("tone", tone)
        for w in (self, self._value):
            w.style().unpolish(w)
            w.style().polish(w)


class MiniBarChart(QWidget):
    """最近 N 天完成量：圆角柱 + 浅网格，无交互。"""

    def __init__(self, days: int = 7, parent=None):
        super().__init__(parent)
        self.days = days
        self.data: list[tuple[date, int]] = []
        self.setMinimumHeight(150)
        self.setMaximumHeight(190)

    def set_data(self, data: list[tuple[date, int]]) -> None:
        self.data = data
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 6, 6, 24, 24
        plot_w = max(1, w - left - right)
        plot_h = max(1, h - top - bottom)
        base_y = h - bottom

        grid_pen = QPen(QColor(t["border"]))
        grid_pen.setWidth(1)
        p.setPen(grid_pen)
        for frac in (0.0, 0.5, 1.0):
            y = base_y - plot_h * frac
            p.drawLine(int(left), int(y), int(w - right), int(y))

        if not self.data:
            return
        counts = [c for _, c in self.data]
        peak = max(counts) if counts else 0
        scale_max = max(peak, 4)

        n = len(self.data)
        slot = plot_w / max(1, n)
        bar_w = min(30.0, slot * 0.46)
        value_font = QFont(self.font())
        value_font.setPixelSize(10)
        label_font = QFont(self.font())
        label_font.setPixelSize(10)
        weekdays = "一二三四五六日"

        for i, (day, count) in enumerate(self.data):
            cx = left + slot * (i + 0.5)
            bar_h = plot_h * (count / scale_max) if scale_max else 0
            bar_h = max(bar_h, 3 if count else 0)
            rect = QRectF(cx - bar_w / 2, base_y - bar_h, bar_w, bar_h)
            color = QColor(t["accent"])
            if day != date.today():
                color.setAlpha(120)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, min(6.0, bar_w / 2), min(6.0, bar_w / 2))

            if count:
                p.setFont(value_font)
                p.setPen(QColor(t["muted"]))
                p.drawText(QRectF(cx - 20, base_y - bar_h - 18, 40, 16),
                           Qt.AlignmentFlag.AlignCenter, str(count))

            label = f"{weekdays[day.weekday()]}" if n == 7 else day.strftime("%m-%d")
            p.setFont(label_font)
            p.setPen(QColor(t["accent"] if day == date.today() else t["faint"]))
            p.drawText(QRectF(cx - 24, base_y + 5, 48, 16),
                       Qt.AlignmentFlag.AlignCenter, label)
        p.end()
