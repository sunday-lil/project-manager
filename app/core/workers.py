"""通用线程封装：任意阻塞函数丢进 QThreadPool，结果通过信号回到 UI 线程。

注意：QRunnable 必须被 Python 强引用到回调送达为止，否则 PySide 会提前回收
wrapper，信号静默丢失（异步操作看起来“永远没反应”）。
"""
import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

log = logging.getLogger(__name__)

# 正在执行的 worker 强引用集合，回调信号送达后延迟释放
_workers: set["FunctionWorker"] = set()


class WorkerSignals(QObject):
    finished = Signal(object)  # 携带函数返回值
    failed = Signal(str)       # 携带异常消息（应为中文）


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()
        self.setAutoDelete(False)  # 生命周期由 _workers 管理

    def run(self) -> None:
        try:
            result = self.fn()
            self._emit(self.signals.finished, result)
        except Exception as e:  # noqa: BLE001 - 统一回传给 UI
            log.error("后台任务失败：%s\n%s", e, traceback.format_exc())
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

    def release(*_args) -> None:
        # 等 UI 线程把这一轮事件处理完再释放，确保其它回调先执行
        QTimer.singleShot(0, lambda: _workers.discard(worker))

    worker.signals.finished.connect(release)
    worker.signals.failed.connect(release)

    _workers.add(worker)
    QThreadPool.globalInstance().start(worker)
    return worker


def active_workers() -> int:
    """测试/诊断用：当前仍被强引用的后台任务数。"""
    return len(_workers)
