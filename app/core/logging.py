"""应用日志：滚动文件 + 未捕获异常落盘。"""
import logging
import logging.handlers
import sys
import traceback

from app.constants import DATA_DIR, LOG_PATH

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        if sys.stderr is not None:  # pythonw 下 stderr 为 None
            root.addHandler(logging.StreamHandler(sys.stderr))
        _configured = True
    except OSError:
        pass  # 日志不可写不应阻塞应用


def install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        logging.getLogger("uncaught").error("".join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def log_path() -> str:
    return str(LOG_PATH)
