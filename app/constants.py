"""全局常量与枚举定义（core 层，不依赖 PySide6）。"""
import os
from pathlib import Path

APP_NAME = "项目管理器"

# 项目根目录（app/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 令牌独立存放的 .env 文件（.gitignore 已排除，绝不入库）
ENV_FILE = PROJECT_ROOT / ".env"

# 数据库路径：%LOCALAPPDATA%\ProjectManager\pm.db
DB_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ProjectManager"
DB_PATH = DB_DIR / "pm.db"

SCHEMA_VERSION = 1


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


class Priority:
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ALL = (HIGH, MEDIUM, LOW)


PRIORITY_LABELS = {Priority.HIGH: "高", Priority.MEDIUM: "中", Priority.LOW: "低"}
PRIORITY_COLORS = {Priority.HIGH: "#e74c3c", Priority.MEDIUM: "#f39c12", Priority.LOW: "#2ecc71"}

# 设置键
SETTING_GITHUB_TOKEN = "github_token"
SETTING_SCAN_ROOT = "scan_root"
SETTING_MERGE_METHOD = "merge_method"
SETTING_REPO_HISTORY = "github_repo_history"

MERGE_METHODS = ("merge", "squash", "rebase")
MERGE_METHOD_LABELS = {"merge": "合并（保留提交）", "squash": "压缩合并", "rebase": "变基合并"}

# 扫描仓库时跳过的目录名
SCAN_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".idea", ".vscode", "dist", "build", ".cache"}
SCAN_MAX_DEPTH = 3

# IDE 多根工作区文件：扫描完成后自动把所有仓库同步进去
WORKSPACE_FILE = Path.home() / "Desktop" / "日常维护.code-workspace"
