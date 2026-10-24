"""生成演示数据库与界面截图（不触碰真实用户数据）。

用法：python scripts/screenshots.py
输出：docs/screenshots/*.png
"""
import os
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = Path(tempfile.mkdtemp(prefix="pm_demo_"))
os.environ["PM_DATA_DIR"] = str(DEMO_DIR / "data")
os.environ["PM_ENV_FILE"] = str(DEMO_DIR / ".env")
os.environ["PM_SYNC_WORKSPACE"] = "0"

sys.path.insert(0, str(ROOT))

from git import Actor, Repo  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.db import init_db  # noqa: E402
from app.core.settings import SettingsStore, set_github_token, set_theme  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.services import repo_service, task_service  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
TODAY = date.today()
ACTOR = Actor("Moxuan", "moxuan@example.com")


def _write(repo: Repo, path: Path, name: str, content: str) -> None:
    target = path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    repo.index.add([name])


def make_repo(base: Path, name: str, remote: str, dirty: bool = False) -> Path:
    path = base / name
    path.mkdir()
    repo = Repo.init(path)
    _write(repo, path, "README.md", f"# {name}\n\n演示仓库。\n")
    _write(repo, path, "app/main.py", "def main():\n    print('hello')\n")
    repo.index.commit("初始化项目结构", author=ACTOR, committer=ACTOR)
    _write(repo, path, "app/service.py", "def sync():\n    return []\n")
    repo.index.commit("添加同步服务", author=ACTOR, committer=ACTOR)
    repo.git.branch("-M", "main")
    repo.create_remote("origin", remote)
    if dirty:
        (path / "app/service.py").write_text("def sync():\n    return [1, 2]\n", encoding="utf-8")
        (path / "TODO.md").write_text("- 补测试\n- 拆分路由\n", encoding="utf-8")
        (path / "app/cache.py").write_text("CACHE = {}\n", encoding="utf-8")
    return path


def seed() -> None:
    init_db()
    set_theme("light")
    SettingsStore.set("sync_workspace", "0")
    set_github_token("ghp_demo_for_screenshots_only")  # 仅演示 .env，不会联网

    projects = DEMO_DIR / "projects"
    projects.mkdir()
    make_repo(projects, "atlas-api", "https://github.com/acme/atlas-api.git", dirty=True)
    make_repo(projects, "orbit-web", "https://github.com/acme/orbit-web.git")
    make_repo(projects, "notes-cli", "https://github.com/acme/notes-cli.git", dirty=True)
    repos = repo_service.upsert_repos([str(projects)])
    by_name = {r.name: r.id for r in repos}

    def day(offset: int) -> str:
        return (TODAY + timedelta(days=offset)).isoformat()

    tasks = [
        ("重写同步队列的重试策略", "按指数退避重试，区分网络错误与业务错误。", "todo", "high",
         day(0), "backend,可靠性", "atlas-api"),
        ("给看板加一个全局搜索", "支持标题、描述、标签的即时过滤。", "todo", "medium",
         day(3), "frontend", "orbit-web"),
        ("整理 v2 发布清单", "核对迁移脚本、截图和 CHANGELOG。", "todo", "medium",
         day(6), "release", None),
        ("补一版 README 截图", "工作台、看板、仓库、GitHub 各一张。", "todo", "low",
         day(2), "docs", "notes-cli"),
        ("评估 SQLite WAL 模式", "多线程读写下是否值得开启。", "todo", "low",
         None, "db", None),
        ("重构 issue 详情渲染", "正文与评论流统一排版。", "todo", "medium",
         day(-2), "frontend", "atlas-api"),
        ("实现工作台仪表盘", "统计卡、今日聚焦、7 日完成趋势。", "doing", "high",
         day(0), "design", "orbit-web"),
        ("接入 Windows DPAPI", "Token 不再明文落盘。", "doing", "high",
         day(1), "security", None),
        ("打磨卡片悬浮态", "边框、层级、拖拽反馈。", "doing", "low",
         day(4), "design", "notes-cli"),
        ("升级数据库 schema v2", "新增 completed_at 与索引。", "done", "high",
         day(-1), "db", None),
        ("完成主题令牌系统", "浅色 / 深色共用一套语义色。", "done", "high",
         day(-2), "design", "orbit-web"),
        ("修复扫描根中文路径", "统一 pathlib 与 UTF-8。", "done", "medium",
         day(-2), "bug", "atlas-api"),
        ("添加任务快速创建", "回车即建，默认进入待办。", "done", "medium",
         day(-3), "frontend", None),
        ("补齐仓库状态列", "改动数、领先、落后与最近提交。", "done", "low",
         day(-5), "git", "notes-cli"),
        ("整理 CHANGELOG", "按版本记录可见变化。", "done", "low",
         day(-6), "docs", None),
        ("修复 Issue 标签过滤", "仅在远端存在同名标签时附加。", "done", "medium",
         day(0), "bug", "atlas-api"),
    ]
    for title, desc, status, prio, due, tags, repo in tasks:
        task = Task(id=None, title=title, description=desc, status=status, priority=prio,
                    due_date=due, tags=tags, repo_id=by_name.get(repo))
        if status == "done":
            task.completed_at = _completed_at(title, tasks)
        task_service.create_task(task)
    SettingsStore.set("github_repo_history", "acme/atlas-api,acme/orbit-web")


def _completed_at(title: str, tasks: list) -> str:
    """让完成时间分布在最近 7 天，趋势图有起伏。"""
    idx = [t[0] for t in tasks].index(title)
    offsets = [-1, -2, -2, -3, -5, -6, 0, -4]
    return (TODAY + timedelta(days=offsets[idx % len(offsets)])).isoformat() + "T18:30:00"


def fake_github(window: MainWindow) -> None:
    info = {
        "owner_repo": "acme/atlas-api", "description": "面向团队的轻量 API 网关，负责鉴权、限流与路由。",
        "stars": 128, "forks": 17, "default_branch": "main",
        "open_issues_count": 5, "open_pulls_count": 2, "language": "Python",
        "updated_at": f"{TODAY:%Y-%m-%d} 21:12", "url": "https://github.com/acme/atlas-api",
    }
    labels = ["bug,backend", "enhancement,frontend", "docs", "performance", "security"]
    issues = []
    for i, (title, author, state) in enumerate([
        ("限流窗口在跨分钟时计数偏移", "lin", "open"),
        ("为 /health 增加依赖检查", "moxuan", "open"),
        ("文档里的环境变量示例过期", "chen", "open"),
        ("连接池在空闲 5 分钟后未释放", "lin", "open"),
        ("补充 OpenAPI 3.1 描述", "yu", "open"),
    ], start=41):
        issues.append({"number": i, "title": title, "state": state, "author": author,
                       "labels": labels[i % len(labels)],
                       "updated_at": f"{TODAY:%m-%d} {9 + i % 10}:24",
                       "url": f"https://github.com/acme/atlas-api/issues/{i}"})
    pulls = [
        {"number": 18, "title": "feat: 支持按标签路由", "state": "open", "author": "moxuan",
         "branch": "feat/label-route → main", "merged": False, "draft": False,
         "body": "支持按标签选择上游，附带单元测试。", "updated_at": f"{TODAY:%m-%d} 20:05",
         "url": "https://github.com/acme/atlas-api/pull/18"},
        {"number": 17, "title": "fix: 限流计数跨分钟偏移", "state": "open", "author": "lin",
         "branch": "fix/rate-window → main", "merged": False, "draft": True,
         "body": "修复窗口边界问题。", "updated_at": f"{TODAY:%m-%d} 18:40",
         "url": "https://github.com/acme/atlas-api/pull/17"},
    ]
    window.github_tab.repo_box.setCurrentText("acme/atlas-api")
    window.github_tab.current_repo = "acme/atlas-api"
    window.github_tab._fill_all((info, issues, pulls))


def grab(window: MainWindow, app: QApplication, name: str) -> None:
    # 等待后台仓库状态/GitHub 回调落位，再截图
    for _ in range(90):
        app.processEvents()
        time.sleep(0.02)
    window.grab().save(str(OUT / f"{name}.png"))
    print("saved", OUT / f"{name}.png")


def main() -> None:
    seed()
    app = QApplication(sys.argv)
    theme.apply(app, "light")
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(1280, 800)
    window.show()
    for _ in range(80):
        app.processEvents()
        time.sleep(0.02)

    window._navigate("dashboard")
    grab(window, app, "dashboard")
    window._navigate("kanban")
    grab(window, app, "kanban")
    window._navigate("repos")
    # 截图里用中性路径，避免暴露本机用户名 / 临时目录
    table = window.repos_tab.table
    for i in range(table.rowCount()):
        name_item = table.item(i, 0)
        path_item = table.item(i, 6)
        if name_item and path_item:
            fake_path = f"C:/Projects/{name_item.text()}"
            path_item.setText(fake_path)
            path_item.setToolTip(fake_path)
    grab(window, app, "repos")
    fake_github(window)
    window._navigate("github")
    window.github_tab.tabs.setCurrentIndex(1)
    grab(window, app, "github-issues")
    window.github_tab.tabs.setCurrentIndex(0)
    grab(window, app, "github-overview")

    from app.ui.dialogs.settings_dialog import SettingsDialog
    dlg = SettingsDialog(window)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    dlg.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    dlg.grab().save(str(OUT / "settings.png"))
    print("saved", OUT / "settings.png")
    dlg.close()

    # 深色主题
    set_theme("dark")
    window._apply_theme("dark", notify=False)
    window._navigate("dashboard")
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)
    grab(window, app, "dashboard-dark")

    window.close()


if __name__ == "__main__":
    main()
