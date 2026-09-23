"""本地 git 仓库：扫描根目录、状态读取、提交历史、分支、fetch、入库。"""
import os
import re
from contextlib import closing
from datetime import datetime
from pathlib import Path

from git import Repo, GitCommandError, InvalidGitRepositoryError

from app.constants import SCAN_SKIP_DIRS, SCAN_MAX_DEPTH
from app.core.db import get_connection
from app.models.repo import LocalRepo, RepoStatus

# https://github.com/owner/repo(.git) 或 git@github.com:owner/repo(.git)
_HTTPS_RE = re.compile(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$")
_REPO_COLS = "id, path, name, remote_url, owner_repo, added_at, last_scanned_at"


def owner_repo_from_url(url: str) -> str:
    """从远程 URL 解析 "owner/repo"；非 GitHub 远程返回空串。"""
    if not url:
        return ""
    m = _HTTPS_RE.search(url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else ""


# ---------- 扫描 ----------

def scan_root(root: str | Path) -> list[dict]:
    """扫描根目录（限深 SCAN_MAX_DEPTH），发现 .git 即停止下探。返回 [{path,name,remote_url,owner_repo}]。"""
    root = Path(root)
    found: list[dict] = []
    if not root.is_dir():
        raise FileNotFoundError(f"目录不存在：{root}")

    for dirpath, dirnames, _ in os.walk(root):
        rel_depth = Path(dirpath).relative_to(root).parts
        if ".git" in dirnames:
            found.append(_repo_info(dirpath))
            dirnames[:] = []  # 是仓库，不再下探
            continue
        if len(rel_depth) >= SCAN_MAX_DEPTH:
            dirnames[:] = []  # 超过深度限制
            continue
        dirnames[:] = [d for d in dirnames if d not in SCAN_SKIP_DIRS and not d.startswith(".")]
    return found


def _repo_info(path: str) -> dict:
    name = Path(path).name
    remote_url, owner_repo = "", ""
    try:
        with Repo(path) as repo:
            if repo.remotes:
                remote_url = repo.remotes[0].url or ""
                owner_repo = owner_repo_from_url(remote_url)
    except Exception:  # noqa: BLE001 - 无远程/坏仓库也要记录
        pass
    return {"path": str(Path(path).resolve()), "name": name,
            "remote_url": remote_url, "owner_repo": owner_repo}


def upsert_repos(roots: str | Path | list[str | Path]) -> list[LocalRepo]:
    """扫描一个或多个根目录并把结果写入 repos 表（路径为准 upsert），同时清理磁盘上已消失的仓库，返回入库后的列表。"""
    if isinstance(roots, (str, Path)):
        roots = [roots]
    now = datetime.now().isoformat(timespec="seconds")
    with closing(get_connection()) as conn:
        for root in roots:
            for info in scan_root(root):
                conn.execute(
                    "INSERT INTO repos (path, name, remote_url, owner_repo, added_at, last_scanned_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(path) DO UPDATE SET name=excluded.name, remote_url=excluded.remote_url, "
                    "owner_repo=excluded.owner_repo, last_scanned_at=excluded.last_scanned_at",
                    (info["path"], info["name"], info["remote_url"], info["owner_repo"], now, now),
                )
        # 清理磁盘上已删除的仓库（关联任务通过 ON DELETE SET NULL 自动解除关联）
        for row in conn.execute("SELECT id, path FROM repos").fetchall():
            if not Path(row["path"]).exists():
                conn.execute("DELETE FROM repos WHERE id = ?", (row["id"],))
        conn.commit()
    return list_repos()


def list_repos() -> list[LocalRepo]:
    with closing(get_connection()) as conn:
        rows = conn.execute(f"SELECT {_REPO_COLS} FROM repos ORDER BY name COLLATE NOCASE").fetchall()
        return [LocalRepo.from_row(r) for r in rows]


def get_repo(repo_id: int) -> LocalRepo | None:
    with closing(get_connection()) as conn:
        row = conn.execute(f"SELECT {_REPO_COLS} FROM repos WHERE id = ?", (repo_id,)).fetchone()
        return LocalRepo.from_row(row) if row else None


# ---------- 状态读取（只读，不触网） ----------

def get_status(path: str) -> RepoStatus:
    st = RepoStatus()
    try:
        with Repo(path) as repo:
            try:
                branch = repo.active_branch.name
            except TypeError:  # 分离头指针
                branch = "HEAD 分离"
            st.branch = branch
            st.is_dirty = repo.is_dirty(untracked_files=True)
            if branch != "HEAD 分离":
                tracking = repo.active_branch.tracking_branch()
                if tracking is not None:
                    counts = repo.git.rev_list("--left-right", "--count",
                                               f"{branch}...{tracking.name}").split()
                    st.ahead, st.behind = int(counts[0]), int(counts[1])
    except InvalidGitRepositoryError:
        st.error = "不是有效的 git 仓库"
    except GitCommandError as e:
        st.error = f"git 命令失败：{e.stderr.strip()[:120] if e.stderr else e.stderr_message}"
    except Exception as e:  # noqa: BLE001
        st.error = f"读取失败：{e}"
    return st


def all_statuses() -> list[tuple[LocalRepo, RepoStatus]]:
    """批量读取所有入库仓库的状态（可能较慢，调用方应放线程池）。"""
    return [(repo, get_status(repo.path)) for repo in list_repos()]


def recent_commits(path: str, limit: int = 50) -> list[dict]:
    """最近提交：[{sha, message, author, time}]。空仓库返回空列表。"""
    with Repo(path) as repo:
        out = []
        try:
            commits = repo.iter_commits(max_count=limit)
        except ValueError:  # 分支无提交（刚 init 的仓库）
            return out
        for c in commits:
            out.append({"sha": c.hexsha[:7],
                        "message": c.message.strip().splitlines()[0] if c.message.strip() else "",
                        "author": c.author.name if c.author else "未知",
                        "time": datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M")})
        return out


def branches(path: str) -> tuple[list[str], list[str]]:
    """(本地分支, 远程分支) 名单。"""
    with Repo(path) as repo:
        local = [h.name for h in repo.heads]
        remote = [r.name for r in repo.remotes[0].refs] if repo.remotes else []
        return local, remote


def fetch(path: str) -> None:
    """拉取远程更新。网络被拦截/失败时抛中文异常，由 UI 降级提示。"""
    try:
        with Repo(path) as repo:
            if not repo.remotes:
                raise RuntimeError("该仓库没有配置远程地址")
            repo.remotes[0].fetch()
    except GitCommandError as e:
        raise RuntimeError(f"fetch 失败（网络问题或无权限）：{(e.stderr or '')[:200]}") from e
