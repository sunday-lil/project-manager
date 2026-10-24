"""应用品牌图标（运行时绘制，无需图片资源）。"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap

from app.ui import theme


def app_icon(size: int = 256) -> QIcon:
    t = theme.tokens()
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = size * 0.06
    rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor(t["accent"]))
    grad.setColorAt(1, QColor(t["accent_hover"]))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(rect, size * 0.23, size * 0.23)

    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(int(size * 0.5))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "P")
    p.end()
    return QIcon(pm)
