"""Issue <-> 本地任务 双向同步编排。"""
from app.models.task import Task
from app.services import repo_service, task_service
from app.services.github_service import GithubService


def _require_repo(repo_id: int):
    repo = repo_service.get_repo(repo_id)
    if repo is None:
        raise RuntimeError("任务未关联本地仓库")
    if not repo.owner_repo:
        raise RuntimeError(f"仓库 {repo.name} 的远程不是 GitHub，无法同步")
    return repo


def pull_issues(gh: GithubService, repo_id: int) -> str:
    """拉取关联仓库的 open issues 生成待办任务；已存在的跳过。返回结果描述。"""
    repo = _require_repo(repo_id)
    issues = gh.list_issues(repo.owner_repo, state="open")
    existing = task_service.issue_numbers_of_repo(repo_id)
    created = 0
    for it in issues:
        if it["number"] in existing:
            continue
        task_service.create_task(Task(
            id=None, title=it["title"], status="todo", priority="medium",
            repo_id=repo_id, issue_number=it["number"], issue_url=it["url"]))
        created += 1
    return f"拉取完成：新建 {created} 个任务，跳过已关联 {len(issues) - created} 个"


def push_task(gh: GithubService, task_id: int) -> str:
    """把本地任务推送到关联仓库创建 Issue，成功后回写编号；已关联的拒绝重复推送。"""
    task = task_service.get_task(task_id)
    if task is None:
        raise RuntimeError("任务不存在")
    if task.issue_number:
        raise RuntimeError(f"任务已关联 Issue #{task.issue_number}，请勿重复推送")
    if not task.repo_id:
        raise RuntimeError("任务未关联仓库，请先编辑任务选择仓库")
    repo = _require_repo(task.repo_id)

    # 标签仅在远端存在同名标签时附加，避免创建失败
    wanted = [t.strip() for t in task.tags.split(",") if t.strip()]
    try:
        available = set(gh.repo_labels(repo.owner_repo)) if wanted else set()
    except RuntimeError:
        available = set()  # 取标签失败不阻塞推送
    labels = [t for t in wanted if t in available]

    result = gh.create_issue(repo.owner_repo, task.title, task.description, labels)
    task_service.link_issue(task_id, result["number"], result["url"])
    return f"已创建 Issue #{result['number']}：{result['url']}"
