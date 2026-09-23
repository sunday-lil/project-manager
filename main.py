"""项目管理器（GitHub + 本地）应用入口。"""
import sys

from PySide6.QtWidgets import QApplication

from app.constants import APP_NAME
from app.core.db import init_db
from app.ui.main_window import MainWindow


def main() -> None:
    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
