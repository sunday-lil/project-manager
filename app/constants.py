"""全局常量与枚举定义（core 层，不依赖 PySide6）。"""
import os
from pathlib import Path

APP_NAME = "项目管理器"
APP_VERSION = "2.0.0"
APP_TAGLINE = "PROJECT COCKPIT"

# 项目根目录（app/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 令牌独立存放的 .env 文件（.gitignore 已排除，绝不入库）；测试/演示可改指向
ENV_FILE = Path(os.environ.get("PM_ENV_FILE") or (PROJECT_ROOT / ".env"))

# 数据目录：默认 %LOCALAPPDATA%\ProjectManager；PM_DATA_DIR 可用于测试/演示隔离
_DATA_DEFAULT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ProjectManager"
DATA_DIR = Path(os.environ.get("PM_DATA_DIR") or _DATA_DEFAULT)
DB_DIR = DATA_DIR  # 兼容旧代码
DB_PATH = DATA_DIR / "pm.db"
LOG_PATH = DATA_DIR / "app.log"
BACKUP_DIR = DATA_DIR / "backups"

SCHEMA_VERSION = 2


class TaskStatus:
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    ALL = (TODO, DOING, DONE)


STATUS_LABELS = {
    TaskStatus.TODO: "待办",
    TaskStatus.DOING: "进行中",
    TaskStatus.DONE: "已完成",
}

STATUS_HINTS = {
    TaskStatus.TODO: "还没开始的事",
    TaskStatus.DOING: "手上的活",
    TaskStatus.DONE: "最近收的尾",
}


class Priority:
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ALL = (HIGH, MEDIUM, LOW)


PRIORITY_LABELS = {Priority.HIGH: "高", Priority.MEDIUM: "中", Priority.LOW: "低"}
PRIORITY_ORDER = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}


class DueFilter:
    ALL = "all"
    TODAY = "today"
    OVERDUE = "overdue"
    WEEK = "week"
    NONE = "none"
    LABELS = {
        ALL: "全部截止日",
        TODAY: "今天到期",
        OVERDUE: "已逾期",
        WEEK: "未来 7 天",
        NONE: "无截止日",
    }


# 设置键
SETTING_GITHUB_TOKEN = "github_token"  # 仅用于旧数据迁移，新值不落库
SETTING_SCAN_ROOT = "scan_root"
SETTING_MERGE_METHOD = "merge_method"
SETTING_REPO_HISTORY = "github_repo_history"
SETTING_THEME = "theme"
SETTING_LAST_PAGE = "last_page"
SETTING_SYNC_WORKSPACE = "sync_workspace"

THEMES = ("system", "light", "dark")
THEME_LABELS = {"system": "跟随系统", "light": "浅色", "dark": "深色"}

MERGE_METHODS = ("merge", "squash", "rebase")
MERGE_METHOD_LABELS = {"merge": "合并（保留提交）", "squash": "压缩合并", "rebase": "变基合并"}

# 扫描仓库时跳过的目录名
SCAN_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".idea", ".vscode",
                  "dist", "build", ".cache", ".next", "target", "out"}
SCAN_MAX_DEPTH = 3

# IDE 多根工作区文件：扫描完成后自动把所有仓库同步进去
WORKSPACE_FILE = Path.home() / "Desktop" / "日常维护.code-workspace"

# 允许用环境变量完全关闭工作区文件写入（打包分发/他人机器更安全）
SYNC_WORKSPACE_ENABLED = os.environ.get("PM_SYNC_WORKSPACE", "1") != "0"
