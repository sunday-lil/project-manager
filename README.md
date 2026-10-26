# 项目管理器 · Project Cockpit

**v2.0.0** · Windows 10/11 桌面应用 · Python 3.10+ / PySide6

把「今天做什么」「代码写到哪了」「远端等我处理什么」收进一个窗口。本地任务看板 + git 仓库状态 + GitHub Issues/PR 的一体化桌面工作台。

![工作台](docs/screenshots/dashboard.png)

## 文档

- [使用指南](docs/USAGE.md)：每个页面的操作、筛选规则、备份恢复与常见问题
- [架构说明](docs/ARCHITECTURE.md)：分层、数据模型、线程模型、主题与测试策略
- [更新日志](CHANGELOG.md)：v1 → v2 的完整变化
- [界面截图](docs/screenshots)：工作台、看板、仓库、GitHub、深色模式、设置

## v2 亮点

- **工作台**：待办 / 进行中 / 逾期 / 本周完成一屏掌握，今日聚焦，7 日完成趋势，仓库健康摘要
- **任务看板**：搜索 + 仓库/优先级/截止日/标签筛选，回车快速添加，跨列拖拽，双击编辑
- **本地仓库**：改动数 / 领先 / 落后 / 最近提交，一键 fetch、`pull --ff-only`、终端 / VS Code 打开
- **GitHub**：本地仓库直接跳转，Issue 详情与评论流、新建 / 关闭 / 重开、PR 详情与合并
- **看得舒服**：统一设计令牌，浅色 / 深色 / 跟随系统随时切换
- **数据安全**：GitHub Token 用 Windows DPAPI 加密，不再明文落盘；数据库升级前自动备份
- **工程质量**：20 个 pytest 用例、单实例锁、滚动日志、崩溃堆栈落盘、环境变量隔离测试数据

## 界面

### 任务看板

![任务看板](docs/screenshots/kanban.png)

筛选与搜索即时生效；卡片左侧色条表示优先级，`←` / `→` 按钮和拖拽都能改变状态。

### 本地仓库

![本地仓库](docs/screenshots/repos.png)

右键可以打开终端、VS Code、资源管理器，或直接 `pull --ff-only`。状态读取全部在后台线程完成，界面不卡。

### GitHub

![GitHub Issues](docs/screenshots/github-issues.png)

![GitHub 概览](docs/screenshots/github-overview.png)

双击 Issue 查看正文与评论，可在详情里直接评论 / 关闭 / 重开。概览页汇总远端数据并支持一键新建 Issue。

### 深色模式

![深色工作台](docs/screenshots/dashboard-dark.png)

### 设置

![设置](docs/screenshots/settings.png)

Token 输入框留空即保持不变；「清除」并保存可移除。已配置的 Token 只显示状态，不回显明文。

## 快捷键

| 快捷键 | 作用 |
| --- | --- |
| `Ctrl+1` ~ `Ctrl+4` | 工作台 / 看板 / 仓库 / GitHub |
| `Ctrl+N` | 新建任务 |
| `Ctrl+K` | 聚焦看板搜索 |
| `Ctrl+E` | 导出任务 CSV |
| `F5` | 刷新当前页 |
| `Ctrl+,` | 设置 |
| `Ctrl+Q` | 退出 |

## 数据与隐私

- **数据库**：`%LOCALAPPDATA%\ProjectManager\pm.db`（SQLite，短连接 + 参数化 SQL）
- **Token**：项目根 `.env` 中的 `GITHUB_TOKEN_DPAPI`，由 Windows DPAPI 按当前用户加密；换机器 / 换 Windows 账户后需重新填写。旧版明文 Token 与数据库旧值会在首次读取时自动迁移并抹掉
- **备份**：`%LOCALAPPDATA%\ProjectManager\backups\`；schema 升级前强制快照，日常启动每天最多一次，保留 10 份
- **日志**：`%LOCALAPPDATA%\ProjectManager\app.log`（单文件 1 MB，滚动 3 份），未捕获异常也会落盘
- **IDE 工作区**：扫描后同步 `~/Desktop/日常维护.code-workspace`，可在设置里关闭
- **单实例**：`%LOCALAPPDATA%\ProjectManager\app.lock`，避免两个窗口同时写库
- **网络**：只访问 GitHub API 以及你自己配置的 git 远程（fetch / pull）；无遥测、无上传

## 升级与恢复

- v1 → v2 首次启动会自动给 `tasks` 增加 `completed_at`，用 `updated_at` 回填已完成任务，并建立索引
- 迁移前会强制备份一份数据库；升级后旧版仍可读取核心数据，但看不到新工作台 / 主题
- 恢复：退出应用，把 `backups\pm-YYYY...db` 复制为 `%LOCALAPPDATA%\ProjectManager\pm.db`，再启动
- 更详细的恢复、换机与常见问题见 [使用指南](docs/USAGE.md)

> 截图中的 `acme/*` 仓库、Issues 与任务均为演示数据，由 `scripts/screenshots.py` 在临时目录生成，不包含个人数据。

## 运行

需要 Python 3.10+、系统 git。Windows 10/11 为完整支持平台；其它系统可运行，但 Token 会退回明文保存。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

也可以双击 `启动项目管理器.bat`（使用 `pythonw` 无控制台启动）。

首次使用在「设置」里填写 GitHub Token（[点此生成](https://github.com/settings/tokens)）。建议 fine-grained token，只授权需要管理的仓库，权限选 Metadata(读) + Issues(读写) + Pull requests(读写)。

## 开发

```bash
pip install -r requirements-dev.txt
pytest                  # 服务层 / 迁移 / 加密 / 后台线程 / 设置 / UI 冒烟
ruff check app tests scripts main.py
python scripts/screenshots.py   # 生成 docs/screenshots（临时演示库，不碰真实数据）
```

测试与截图都通过 `PM_DATA_DIR` / `PM_ENV_FILE` 指向临时目录；`PM_SYNC_WORKSPACE=0` 可禁止改写 IDE 工作区文件。测试不读取也不修改真实 `pm.db` / `.env`。

```
app/
├── constants.py          # 版本、数据路径、枚举、设置键
├── core/                 # db 迁移 / 备份 / DPAPI / 日志 / 线程 / 桌面 shell
├── models/               # Task / LocalRepo / RepoStatus
├── services/             # 任务、仓库、GitHub、统计、导出、同步
└── ui/
    ├── theme.py          # 设计令牌 + 全局 QSS + 调色板
    ├── brand.py          # 运行时绘制的应用图标
    ├── main_window.py    # 侧边栏 + 页面栈 + 菜单 / 快捷键
    ├── tabs/             # 工作台 / 看板 / 仓库 / GitHub
    ├── dialogs/          # 任务 / 仓库 / 设置 / Issue / PR / 关于
    └── widgets/          # 任务卡片、统计卡、迷你柱状图、页头
```

分层约定：UI 只调 services；跨页面通信走信号；GitHub / 扫描 / git 状态一律进线程池。细节见 [架构说明](docs/ARCHITECTURE.md)。

## 已知限制

- GitHub 的 Issue / PR 列表最多拉取 100 条，Issue 评论最多展示 50 条
- 不提供 commit / push / 创建 PR 的界面；这些操作仍在 IDE 或命令行完成
- 看板只改变任务状态，列内顺序不持久化
- 单窗口、单实例；不做云同步 / 多设备同步
- 完整限制与后续方向见 [架构说明](docs/ARCHITECTURE.md#9-已知限制与后续方向)

## 技术栈

Python 3.10+ · PySide6（Essentials）· PyGithub · GitPython · SQLite · truststore（Windows 系统证书链）

## License

[MIT](LICENSE)
