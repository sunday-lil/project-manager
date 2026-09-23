"""本地仓库数据模型。"""
from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class LocalRepo:
    id: Optional[int]
    path: str
    name: str = ""
    remote_url: str = ""
    owner_repo: str = ""
    added_at: Optional[str] = None
    last_scanned_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "LocalRepo":
        return cls(**dict(row))


@dataclass
class RepoStatus:
    """单个本地仓库的 git 状态快照。"""

    branch: str = ""
    is_dirty: bool = False
    ahead: Optional[int] = None   # 本地领先远程的提交数；None 表示无跟踪分支
    behind: Optional[int] = None  # 本地落后远程的提交数
    error: str = ""               # 非空表示读取失败（中文消息）
