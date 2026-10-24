"""项目管理器（GitHub + 本地）应用入口。"""
import sys

# 优先用 Windows 系统证书存储做 TLS 验证（国内网络访问 GitHub 证书链间歇性不完整时 certifi 会挂）
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from app.constants import APP_NAME, DATA_DIR
from app.core.backup import backup_db
from app.core.db import init_db
from app.core.logging import install_excepthook, setup_logging
from app.core.settings import get_theme
from app.ui import theme
from app.ui.brand import app_icon
from app.ui.main_window import MainWindow


def main() -> None:
    setup_logging()
    install_excepthook()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("sunday-lil")
    app.setStyle("Fusion")
    theme.apply(app, get_theme())
    app.setWindowIcon(app_icon())

    try:
        init_db()
        backup_db()  # 每天最多一次自动快照
    except Exception as e:  # noqa: BLE001 - 启动失败要给用户看得懂的提示
        QMessageBox.critical(None, APP_NAME, f"数据库初始化失败：\n{e}")
        raise

    # 单实例：避免两个窗口同时写同一个 SQLite
    lock = QLockFile(str(DATA_DIR / "app.lock"))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        QMessageBox.warning(None, APP_NAME, "项目管理器已经在运行，请切换回已打开的窗口。")
        return

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
