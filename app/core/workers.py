"""通用线程封装：任意阻塞函数丢进 QThreadPool，结果通过信号回到 UI 线程。"""
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.constants import DB_DIR

_LOG_FILE = DB_DIR / "error.log"


def _log_error(exc: Exception) -> None:
    """把后台线程异常完整堆栈写入日志文件，便于定位问题。"""
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n\n")
    except OSError:
        pass  # 日志失败不影响主流程


class WorkerSignals(QObject):
    finished = Signal(object)  # 携带函数返回值
    failed = Signal(str)       # 携带异常消息（应为中文）


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn()
            self._emit(self.signals.finished, result)
        except Exception as e:  # noqa: BLE001 - 统一回传给 UI
            _log_error(e)
            self._emit(self.signals.failed, str(e) or e.__class__.__name__)

    @staticmethod
    def _emit(signal, arg) -> None:
        try:
            signal.emit(arg)
        except RuntimeError:  # 接收方已销毁（如应用退出），静默放弃
            pass


def run_async(fn: Callable[[], Any], on_ok: Callable | None = None,
              on_err: Callable[[str], None] | None = None) -> FunctionWorker:
    """在全局线程池执行阻塞函数 fn，成功/失败分别回调（回调在 UI 线程执行）。"""
    worker = FunctionWorker(fn)
    if on_ok is not None:
        worker.signals.finished.connect(on_ok)
    if on_err is not None:
        worker.signals.failed.connect(on_err)
    QThreadPool.globalInstance().start(worker)
    return worker
