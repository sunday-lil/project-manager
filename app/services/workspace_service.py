"""IDE 多根工作区文件同步：把 repos 表里的仓库写成 .code-workspace。

folders 以 repos 表为准重建（IDE 侧手工加的目录会被管理器覆盖），
settings 等其它键保留；文件不存在时自动创建。
"""
import json

from app.constants import WORKSPACE_FILE
from app.models.repo import LocalRepo

_FALLBACK_SETTINGS = {"git.autofetch": True}


def _folder_entry(repo: LocalRepo) -> dict:
    """仓库 → 工作区文件夹项，name 标注 GitHub 仓库名。"""
    if repo.owner_repo:
        short = repo.owner_repo.split("/")[-1]
        name = f"{repo.name}（{short}）"
    else:
        name = repo.name or repo.path
    return {"name": name, "path": repo.path}


def sync_workspace(repos: list[LocalRepo]) -> str:
    """把仓库列表写入工作区文件，返回描述信息。"""
    data: dict = {}
    if WORKSPACE_FILE.exists():
        try:
            data = json.loads(WORKSPACE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}  # 文件损坏则重建
    if not isinstance(data, dict):
        data = {}
    data["folders"] = [_folder_entry(r) for r in repos]
    if "settings" not in data:
        data["settings"] = dict(_FALLBACK_SETTINGS)
    WORKSPACE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(WORKSPACE_FILE)
