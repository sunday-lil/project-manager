"""工作台：一眼看清今天该做什么、这周做了多少、仓库是否健康。"""
import os
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.constants import PRIORITY_LABELS, STATUS_LABELS
from app.core.workers import run_async
from app.models.task import Task
from app.services import repo_service, stats_service
from app.ui import theme
from app.ui.widgets.common import MiniBarChart, PageHeader, StatCard

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 6:
        return "夜深了"
    if hour < 12:
        return "早上好"
    if hour < 14:
        return "中午好"
    if hour < 18:
        return "下午好"
    return "晚上好"


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()


class FocusRow(QFrame):
    """今日聚焦里的一行任务，点击进入编辑。"""

    clicked = Signal(int)

    def __init__(self, task: Task, repo_name: str, parent=None):
        super().__init__(parent)
        self.task = task
        self.setProperty("role", "row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(task.description or task.title)

        title = QLabel(task.title)
        title.setProperty("role", "rowTitle")
        title.setWordWrap(True)

        meta_bits = [STATUS_LABELS.get(task.status, task.status)]
        if repo_name:
            meta_bits.append(repo_name)
        if task.issue_number:
            meta_bits.append(f"#{task.issue_number}")
        meta = QLabel(" · ".join(meta_bits))
        meta.setProperty("role", "faint")

        left = QVBoxLayout()
        left.setSpacing(1)
        left.addWidget(title)
        left.addWidget(meta)

        chips = QHBoxLayout()
        chips.setSpacing(5)
        prio = QLabel(f"{PRIORITY_LABELS.get(task.priority, task.priority)}优先级")
        prio.setProperty("role", "chip")
        prio.setProperty("tone", {"high": "danger", "medium": "warning"}.get(task.priority, "success"))
        chips.addWidget(prio)
        chips.addStretch(1)

        due = QLabel(self._due_text(task))
        due.setProperty("role", "chip")
        due.setProperty("tone", self._due_tone(task))
        chips.addWidget(due)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addLayout(chips)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(10)
        row.addLayout(left, stretch=1)
        row.addLayout(right)

    @staticmethod
    def _due_text(task: Task) -> str:
        if not task.due_date:
            return "无截止日"
        try:
            y, m, d = map(int, task.due_date.split("-"))
            due = date(y, m, d)
        except ValueError:
            return task.due_date
        delta = (due - date.today()).days
        if delta < 0:
            return f"逾期 {-delta} 天"
        if delta == 0:
            return "今天到期"
        if delta == 1:
            return "明天到期"
        return f"{due.month}/{due.day} 到期"

    @staticmethod
    def _due_tone(task: Task) -> str:
        if not task.due_date:
            return ""
        if task.due_date < date.today().isoformat():
            return "danger"
        if task.due_date == date.today().isoformat():
            return "warning"
        return ""

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.task.id)
        super().mouseReleaseEvent(event)


class DashboardTab(QWidget):
    status_message = Signal(str)
    new_task_requested = Signal()
    open_kanban = Signal()
    open_repos = Signal()
    task_activated = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._repo_loading = False

        self.header = PageHeader("", "")
        new_btn = QPushButton("＋ 新建任务")
        new_btn.setProperty("variant", "primary")
        new_btn.clicked.connect(self.new_task_requested)
        self.header.add_action(new_btn)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setProperty("variant", "ghost")
        refresh_btn.clicked.connect(self.refresh)
        self.header.add_action(refresh_btn)

        # 统计卡
        self.card_todo = StatCard("待办", tone="accent")
        self.card_doing = StatCard("进行中", tone="warning")
        self.card_due = StatCard("逾期", tone="danger")
        self.card_done = StatCard("本周完成", tone="success", hint="最近 7 天")
        cards = QHBoxLayout()
        cards.setSpacing(14)
        for card in (self.card_todo, self.card_doing, self.card_due, self.card_done):
            cards.addWidget(card, stretch=1)

        # 今日聚焦
        self.focus_card = QFrame()
        self.focus_card.setProperty("role", "card")
        focus_title = QLabel("今日聚焦")
        focus_title.setProperty("role", "h2")
        self.focus_count = QLabel("")
        self.focus_count.setProperty("role", "chip")
        focus_more = QPushButton("查看看板 →")
        focus_more.setProperty("variant", "link")
        focus_more.clicked.connect(self.open_kanban)
        fhead = QHBoxLayout()
        fhead.setSpacing(8)
        fhead.addWidget(focus_title)
        fhead.addWidget(self.focus_count)
        fhead.addStretch(1)
        fhead.addWidget(focus_more)

        self.focus_box = QVBoxLayout()
        self.focus_box.setSpacing(0)
        flayout = QVBoxLayout(self.focus_card)
        flayout.setContentsMargins(16, 14, 16, 12)
        flayout.setSpacing(8)
        flayout.addLayout(fhead)
        flayout.addLayout(self.focus_box, stretch=1)
        self.focus_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 本周完成
        chart_card = QFrame()
        chart_card.setProperty("role", "card")
        chart_title = QLabel("本周完成")
        chart_title.setProperty("role", "h2")
        self.chart_total = QLabel("")
        self.chart_total.setProperty("role", "chip")
        self.chart_total.setProperty("tone", "success")
        chead = QHBoxLayout()
        chead.addWidget(chart_title)
        chead.addStretch(1)
        chead.addWidget(self.chart_total)
        self.chart = MiniBarChart(7)
        clayout = QVBoxLayout(chart_card)
        clayout.setContentsMargins(16, 14, 14, 10)
        clayout.setSpacing(6)
        clayout.addLayout(chead)
        clayout.addWidget(self.chart)
        self.chart_hint = QLabel("")
        self.chart_hint.setProperty("role", "faint")
        clayout.addWidget(self.chart_hint)

        # 仓库健康
        repo_card = QFrame()
        repo_card.setProperty("role", "card")
        repo_title = QLabel("仓库健康")
        repo_title.setProperty("role", "h2")
        repo_more = QPushButton("全部仓库 →")
        repo_more.setProperty("variant", "link")
        repo_more.clicked.connect(self.open_repos)
        rhead = QHBoxLayout()
        rhead.addWidget(repo_title)
        rhead.addStretch(1)
        rhead.addWidget(repo_more)

        self.repo_stats = QLabel("读取中…")
        self.repo_stats.setWordWrap(True)
        self.repo_stats.setTextFormat(Qt.TextFormat.RichText)
        self.repo_attention = QLabel("")
        self.repo_attention.setProperty("role", "faint")
        self.repo_attention.setWordWrap(True)

        rlayout = QVBoxLayout(repo_card)
        rlayout.setContentsMargins(16, 14, 16, 14)
        rlayout.setSpacing(8)
        rlayout.addLayout(rhead)
        rlayout.addWidget(self.repo_stats)
        rlayout.addWidget(self.repo_attention)
        rlayout.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(14)
        right.addWidget(chart_card)
        right.addWidget(repo_card)

        grid = QGridLayout()
        grid.setSpacing(14)
        grid.addWidget(self.focus_card, 0, 0)
        grid.addLayout(right, 0, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(16)
        root.addWidget(self.header)
        root.addLayout(cards)
        root.addLayout(grid, stretch=1)

        self.refresh()

    # ---------- 刷新 ----------

    def refresh(self) -> None:
        now = date.today()
        self.header.title.setText(f"{_greeting()}，{self._user_name()}")
        self.header.set_subtitle(
            f"{now.year} 年 {now.month} 月 {now.day} 日 · {_WEEKDAYS[now.weekday()]} · 把重要的事放进今天")

        stats = stats_service.overview()
        self.card_todo.set_value(stats.todo, "共 %d 个任务" % stats.total if stats.total else "还没有任务")
        self.card_doing.set_value(stats.doing, "专注当下")
        due_hint = f"另有 {stats.due_today} 个今天到期" if stats.due_today else "没有今天到期"
        self.card_due.set_value(stats.overdue, due_hint)
        self.card_done.set_value(stats.completed_week, "最近 7 天")

        self._fill_focus()
        trend = stats_service.completion_trend(7)
        self.chart.set_data(trend)
        total = sum(n for _, n in trend)
        self.chart_total.setText(f"{total} 个")
        self.chart_hint.setText("完成得不错，继续保持节奏" if total else "完成第一件事，曲线就会动起来")
        self._load_repo_health()

    @staticmethod
    def _user_name() -> str:
        name = (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip()
        if not name or name.lower() in {"trustedinstaller", "system", "administrator",
                                        "default", "localservice", "networkservice"}:
            return "朋友"
        return name

    def _fill_focus(self) -> None:
        _clear(self.focus_box)
        tasks = stats_service.focus_tasks(6)
        repos = {r.id: r.name for r in repo_service.list_repos() if r.id}
        self.focus_count.setText(f"{len(tasks)} 件")
        if not tasks:
            self._set_chip_tone(self.focus_count, "success")
            done = QLabel("✓")
            done.setAlignment(Qt.AlignmentFlag.AlignCenter)
            done.setProperty("role", "stat")
            done.setProperty("tone", "success")
            tip = QLabel("今天没有燃眉之急\n可以先挑一件想做的小事")
            tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tip.setProperty("role", "empty")
            self.focus_box.addStretch(1)
            self.focus_box.addWidget(done)
            self.focus_box.addWidget(tip)
            self.focus_box.addStretch(1)
        else:
            self._set_chip_tone(self.focus_count, "")
            for task in tasks:
                row = FocusRow(task, repos.get(task.repo_id, ""))
                row.clicked.connect(self.task_activated)
                self.focus_box.addWidget(row)
            self.focus_box.addStretch(1)

        recent = stats_service.recent_completed(3)
        if recent:
            divider = QFrame()
            divider.setProperty("role", "hline")
            self.focus_box.addWidget(divider)
            label = QLabel("最近完成")
            label.setProperty("role", "section")
            self.focus_box.addWidget(label)
            for task in recent:
                self.focus_box.addWidget(self._recent_row(task))

    @staticmethod
    def _recent_row(task: Task) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)
        check = QLabel("✓")
        check.setProperty("role", "chip")
        check.setProperty("tone", "success")
        title = QLabel(task.title)
        title.setProperty("role", "muted")
        when = QLabel((task.completed_at or "")[:10].replace("-", "/"))
        when.setProperty("role", "faint")
        layout.addWidget(check)
        layout.addWidget(title, stretch=1)
        layout.addWidget(when)
        return row

    def _load_repo_health(self) -> None:
        if self._repo_loading:
            return
        self._repo_loading = True
        repos = repo_service.list_repos()
        if not repos:
            self.repo_stats.setText("还没有扫描本地仓库")
            self.repo_attention.setText("在「本地仓库」里添加一个扫描目录即可开始")
            self._repo_loading = False
            return
        self.repo_stats.setText("读取中…")

        def work():
            return repo_service.all_statuses()

        def done(pairs):
            self._repo_loading = False
            dirty = [r for r, s in pairs if s.is_dirty]
            behind = [(r, s) for r, s in pairs if (s.behind or 0) > 0]
            changed = sum(s.dirty_count for _, s in pairs)
            self.repo_stats.setText(
                f"<b style='font-size:18px'>{len(pairs)}</b> 个仓库 &nbsp;·&nbsp; "
                f"<span style='color:{theme.tone('warning')}'><b>{len(dirty)}</b> 个有改动</span>"
                f" &nbsp;·&nbsp; "
                f"<span style='color:{theme.tone('danger')}'><b>{len(behind)}</b> 个落后远程</span>")
            attention = []
            for repo, st in sorted(pairs, key=lambda p: ((p[1].behind or 0) + (p[1].dirty_count > 0)),
                                    reverse=True)[:3]:
                bits = []
                if st.dirty_count:
                    bits.append(f"{st.dirty_count} 处未提交")
                if (st.behind or 0) > 0:
                    bits.append(f"落后 {st.behind}")
                if bits:
                    attention.append(f"{repo.name} · {'，'.join(bits)}")
            if attention:
                self.repo_attention.setText("需要留意：" + "；".join(attention))
            else:
                self.repo_attention.setText(f"全部干净，共 {changed} 处未提交改动" if changed else "全部干净，节奏很好")
            self.status_message.emit(f"仓库状态已更新：{len(pairs)} 个仓库")

        def failed(err):
            self._repo_loading = False
            self.repo_stats.setText(f"读取失败：{err}")
            self.repo_attention.setText("")

        run_async(work, on_ok=done, on_err=failed)

    @staticmethod
    def _set_chip_tone(label: QLabel, value: str) -> None:
        label.setProperty("tone", value)
        theme.repolish(label)
