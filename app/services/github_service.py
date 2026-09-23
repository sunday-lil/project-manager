"""PyGithub 封装：所有方法阻塞式执行（供线程池调用），异常消息统一中文。"""
import functools
import time
from typing import Optional

import requests
from github import Github, Auth, GithubException, RateLimitExceededException
from github.GithubException import BadCredentialsException, UnknownObjectException

_MAX_ITEMS = 100  # 列表最多拉取条数（控制分页请求数，避免快速耗尽 API 配额）


def _retry_network(times: int = 2, delay: float = 1.0):
    """读操作装饰器：网络瞬断（连接中断/超时）自动重试。"""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last = None
            for attempt in range(times + 1):
                try:
                    return fn(*args, **kwargs)
                except requests.RequestException as e:  # 网络瞬断，值得重试
                    last = e
                    if attempt < times:
                        time.sleep(delay)
            raise RuntimeError(f"网络连接失败（已重试 {times} 次）") from last
        return wrapper
    return deco


def _friendly_error(e: Exception, action: str) -> str:
    """把 PyGithub 异常翻译成用户能看懂的中文提示。"""
    if isinstance(e, BadCredentialsException):
        return f"{action}失败：Token 无效或已过期，请在设置中更新"
    if isinstance(e, RateLimitExceededException):
        return f"{action}失败：GitHub API 限流（匿名 60 次/小时，配置 Token 后为 5000 次/小时），请稍后再试"
    if isinstance(e, UnknownObjectException):
        return f"{action}失败：仓库不存在或无权访问（检查 owner/repo 与 Token 权限）"
    if isinstance(e, GithubException):
        return f"{action}失败：GitHub 返回 {e.status}"
    msg = str(e)
    if "Max retries" in msg or "timed out" in msg or "Connection" in msg:
        return f"{action}失败：网络连接失败"
    return f"{action}失败：{msg[:200]}"


class GithubService:
    """需要 token 才能读私有仓库/执行写操作；匿名只读公开仓库（限流 60 次/小时）。"""

    def __init__(self, token: Optional[str] = None):
        self._token = token.strip() if token and token.strip() else None
        auth = Auth.Token(self._token) if self._token else None
        # retry=2：限流/网络失败快速抛出，不做无限退避等待
        self._gh = Github(auth=auth, retry=2)

    # ---------- 仓库 ----------

    @_retry_network()
    def get_repo_info(self, owner_repo: str) -> dict:
        """仓库概览信息。"""
        try:
            r = self._gh.get_repo(owner_repo)
            open_pulls = 0
            for _ in r.get_pulls(state="open"):
                open_pulls += 1
                if open_pulls >= _MAX_ITEMS:
                    break
            return {"owner_repo": owner_repo, "description": r.description or "（无描述）",
                    "stars": r.stargazers_count, "forks": r.forks_count,
                    "default_branch": r.default_branch,
                    "open_issues_count": r.open_issues_count,  # 含 PR
                    "open_pulls_count": open_pulls,
                    "language": r.language or "—", "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M"),
                    "url": r.html_url}
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "获取仓库信息")) from e

    # ---------- Issues（读） ----------

    @_retry_network()
    def list_issues(self, owner_repo: str, state: str = "open") -> list[dict]:
        """issue 列表（过滤掉混入的 PR）。不用切片：PyGithub 的 _Slice 迭代在分页边界会越界。"""
        try:
            repo = self._gh.get_repo(owner_repo)
            out = []
            for it in repo.get_issues(state=state):
                if len(out) >= _MAX_ITEMS:
                    break
                if it.pull_request is not None:  # get_issues 会混入 PR
                    continue
                out.append({"number": it.number, "title": it.title, "state": it.state,
                            "author": it.user.login if it.user else "",
                            "labels": ",".join(l.name for l in it.labels),
                            "updated_at": it.updated_at.strftime("%m-%d %H:%M"),
                            "url": it.html_url})
            return out
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "获取 Issues")) from e

    # ---------- Pull Requests（读） ----------

    @_retry_network()
    def list_pulls(self, owner_repo: str, state: str = "open") -> list[dict]:
        try:
            repo = self._gh.get_repo(owner_repo)
            out = []
            for p in repo.get_pulls(state=state):
                if len(out) >= _MAX_ITEMS:
                    break
                out.append({"number": p.number, "title": p.title, "state": p.state,
                            "author": p.user.login if p.user else "",
                            "branch": f"{p.head.ref} → {p.base.ref}",
                            "merged": p.merged_at is not None,  # 列表接口含 merged_at，避免逐条补全请求
                            "draft": p.draft,
                            "updated_at": p.updated_at.strftime("%m-%d %H:%M"),
                            "url": p.html_url})
            return out
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "获取 Pull Requests")) from e

    # ---------- 写操作 ----------

    def create_issue(self, owner_repo: str, title: str, body: str = "",
                     labels: Optional[list[str]] = None) -> dict:
        try:
            repo = self._gh.get_repo(owner_repo)
            it = repo.create_issue(title=title, body=body, labels=labels or [])
            return {"number": it.number, "url": it.html_url}
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "创建 Issue")) from e

    def set_issue_state(self, owner_repo: str, number: int, open_: bool) -> None:
        action = "重开" if open_ else "关闭"
        try:
            self._gh.get_repo(owner_repo).get_issue(number).edit(state="open" if open_ else "closed")
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, f"{action} Issue")) from e

    def add_comment(self, owner_repo: str, number: int, body: str) -> None:
        try:
            self._gh.get_repo(owner_repo).get_issue(number).create_comment(body)
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "添加评论")) from e

    def merge_pull(self, owner_repo: str, number: int, method: str = "merge") -> None:
        """method: merge / squash / rebase。"""
        try:
            pr = self._gh.get_repo(owner_repo).get_pull(number)
            if pr.state != "open":
                raise RuntimeError(f"PR #{number} 已关闭，无法合并")
            ok, _, msg = pr.merge(merge_method=method)
            if not ok:
                raise RuntimeError(f"合并失败：{msg}")
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "合并 PR")) from e

    def close_pull(self, owner_repo: str, number: int) -> None:
        try:
            self._gh.get_repo(owner_repo).get_pull(number).edit(state="closed")
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "关闭 PR")) from e

    @_retry_network()
    def repo_labels(self, owner_repo: str) -> list[str]:
        """仓库现有标签名（推送任务时用于过滤）。"""
        try:
            return [l.name for l in self._gh.get_repo(owner_repo).get_labels()]
        except GithubException as e:
            raise RuntimeError(_friendly_error(e, "获取标签")) from e
