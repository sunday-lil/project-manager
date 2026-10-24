"""本地 git 仓库扫描、状态、历史与工作区文件。"""
import json
from pathlib import Path

from git import Actor, Repo

from app.models.repo import LocalRepo
from app.services import repo_service, workspace_service

ACTOR = Actor("Tester", "tester@example.com")


def init_repo(path: Path, remote: str = "", dirty: bool = False) -> Repo:
    path.mkdir(parents=True)
    repo = Repo.init(path)
    (path / "README.md").write_text("# demo\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("init", author=ACTOR, committer=ACTOR)
    repo.git.branch("-M", "main")
    if remote:
        repo.create_remote("origin", remote)
    if dirty:
        (path / "README.md").write_text("# changed\n", encoding="utf-8")
        (path / "new.txt").write_text("new\n", encoding="utf-8")
    return repo


def test_scan_upsert_and_cleanup(isolated_db, tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    init_repo(root / "group" / "alpha", "git@github.com:acme/alpha.git")
    init_repo(root / "beta", "https://github.com/acme/beta.git")
    init_repo(root / "gamma")  # 无远程

    repos = repo_service.upsert_repos([str(root)])
    names = {r.name: r for r in repos}
    assert set(names) == {"alpha", "beta", "gamma"}
    assert names["alpha"].owner_repo == "acme/alpha"
    assert names["beta"].owner_repo == "acme/beta"
    assert names["gamma"].owner_repo == ""

    # 磁盘删除后自动清理（Windows 上 git 对象是只读的，需要先去掉只读位）
    import os
    import shutil
    import stat

    def force_remove(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(root / "beta", onerror=force_remove)
    repos = repo_service.upsert_repos([str(root)])
    assert "beta" not in {r.name for r in repos}


def test_status_commits_branches(isolated_db, tmp_path):
    repo_path = tmp_path / "dirty"
    init_repo(repo_path, "https://github.com/acme/dirty.git", dirty=True)
    repo_service.upsert_repos([str(tmp_path)])

    status = repo_service.get_status(str(repo_path))
    assert status.error == ""
    assert status.branch == "main"
    assert status.is_dirty
    assert status.dirty_count >= 2
    assert status.ahead is None  # 没有跟踪分支

    commits = repo_service.recent_commits(str(repo_path))
    assert commits and commits[0]["message"] == "init"

    local, remote = repo_service.branches(str(repo_path))
    assert "main" in local

    bad = repo_service.get_status(str(tmp_path / "nope"))
    assert bad.error


def test_workspace_sync_preserves_settings(isolated_db, tmp_path, monkeypatch):
    target = tmp_path / "demo.code-workspace"
    target.write_text(json.dumps({"settings": {"git.autofetch": False},
                                  "folders": [{"path": "old"}]}), encoding="utf-8")
    monkeypatch.setattr(workspace_service, "WORKSPACE_FILE", target)

    repos = [LocalRepo(id=1, path=str(tmp_path / "alpha"), name="alpha",
                       owner_repo="acme/alpha")]
    workspace_service.sync_workspace(repos)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["settings"] == {"git.autofetch": False}
    assert data["folders"] == [{"name": "alpha（alpha）", "path": str(tmp_path / "alpha")}]
