# 架构说明

本文记录 v2.0.0 的分层、数据模型、并发模型与关键设计取舍。面向维护者，不要求阅读后才能使用。

## 1. 分层

```
┌──────────────────────────────────────────────┐
│ ui/                                          │
│  main_window · tabs · dialogs · widgets      │
│  theme / brand                               │
└───────────────┬──────────────────────────────┘
                │ 只调用 services；跨页面用 Signal
┌───────────────▼──────────────────────────────┐
│ services/                                    │
│  task · repo · github · sync · stats · export│
│  纯 Python，不 import PySide6                 │
└───────────────┬──────────────────────────────┘
                │
┌───────────────▼──────────────────────────────┐
│ core/                                        │
│  db 迁移 · backup · secrets(DPAPI) · logging │
│  workers(QThreadPool) · shell(桌面交互)       │
├──────────────────────────────────────────────┤
│ models/  Task · LocalRepo · RepoStatus       │
│ constants.py 路径 / 枚举 / 设置键（不含 Qt）  │
└──────────────────────────────────────────────┘
```

约束：

- `services` 不依赖 Qt，可被 pytest 直接测试
- 数据库连接只在单次方法内创建 / 关闭，不跨线程共享
- UI 的所有阻塞工作（git、GitHub、扫描）通过 `run_async` 进入线程池
- 跨页面通信只走信号，不直接互相调用（`MainWindow` 负责路由）

## 2. 数据模型

数据库：`%LOCALAPPDATA%\ProjectManager\pm.db`，SQLite，`PRAGMA foreign_keys = ON`。

```sql
repos(
  id, path UNIQUE, name, remote_url, owner_repo,
  added_at, last_scanned_at
)

tasks(
  id, title, description,
  status: todo / doing / done,
  priority: high / medium / low,
  due_date, tags, repo_id -> repos(id) ON DELETE SET NULL,
  issue_number, issue_url, synced_at,
  completed_at,
  created_at, updated_at
)

settings(key PRIMARY KEY, value)
```

索引：`tasks(status)`、`tasks(repo_id)`、`tasks(due_date)`、`tasks(completed_at)`。

### 2.1 `completed_at` 语义

- 任务进入 `done`：写入当前时间（已有值不覆盖）
- 任务移出 `done`：清空
- 已完成任务被编辑：保留原完成时间
- v2 迁移时：已完成任务的 `completed_at` 回填为 `updated_at`，作为趋势图基线

### 2.2 迁移

`PRAGMA user_version` 控制版本：

- v0：执行完整 DDL，直接写入当前版本
- v1 → v2：`ALTER TABLE tasks ADD COLUMN completed_at`、回填、建索引
- 升级前如果数据库已存在且版本 > 0：强制 `backup_db(force=True)`

迁移只加列 / 索引，不删除数据；旧版代码仍能读写核心字段。

### 2.3 备份

`core/backup.py` 使用 SQLite 在线备份 API（`src.backup(dst)`）：

- 启动时每天最多一次
- 迁移前强制一次
- 最多保留 10 份，按 mtime 滚动删除
- 失败静默返回 `None`，绝阻塞启动

## 3. 并发模型

### 3.1 Worker

`core/workers.py`：

```python
worker = FunctionWorker(fn)      # QRunnable
worker.signals.finished/failed   # QObject Signal
_workers.add(worker)             # 必须强引用
QThreadPool.globalInstance().start(worker)
# 回调送达后 QTimer.singleShot(0, discard)
```

**关键修复**：PySide 的 `QRunnable` 如果只被 C++ 线程池持有，Python wrapper 可能被提前回收，信号静默丢失；表现是异步操作“永远停在读取中”。因此：

- `setAutoDelete(False)`，生命周期由 `_workers` 管理
- 回调在主线程执行（Qt queued connection）
- 回调送达后延迟一轮事件循环再释放

测试 `tests/test_workers_ui.py::test_run_async_delivers_result` 覆盖该回归。

### 3.2 UI 线程与数据库

- 所有 SQLite 操作都在 UI 线程（任务 CRUD 很快）
- 每个方法新建短连接，`with closing(get_connection())`
- 不把 connection 传进 worker，避免 `check_same_thread` 与锁问题

### 3.3 竞态处理

- 仓库状态按 **repo.id → row** 映射，而不是行号
- 每次刷新递增 `_load_gen`，旧结果回来时直接丢弃
- 看板 / 仓库表格的列表在异步期间可能重建；回调通过 id 查找，找不到就跳过

## 4. GitHub 层

`services/github_service.py` 封装 PyGithub：

- 读操作带 `_retry_network`（连接中断 / 超时重试 2 次）
- 写操作不自动重试，避免重复创建 Issue / 评论
- 异常统一翻译成中文：无效 Token、限流、仓库不存在、网络失败
- Issue / PR 列表最多请求 100 条；Issue 评论最多 50 条
- `get_issues` 会混入 PR，按 `pull_request` 字段过滤
- `merge_pull` 校验 PR 仍为 open，按设置选择 merge / squash / rebase

Issue / PR 原始 dict 挂在 `QTableWidgetItem` 的 `UserRole` 上，避免从显示文本反解析状态。

## 5. UI 与主题

### 5.1 设计令牌

`ui/theme.py` 定义 `LIGHT` / `DARK` 两组语义色（背景、表面、边框、文本、强调色、语义色），以及：

- `_palette()`：设置 QPalette（含 Link / LinkVisited，修复 Fusion 下链接发黄）
- `_qss()`：全局样式表，控件通过 objectName / 动态属性命中：
  - `QLabel[role="h1"/"muted"/"chip"]`
  - `QFrame[role="card"/"column"/"row"]`
  - `QPushButton[variant="primary"/"ghost"/"danger"/"link"]`
  - `QPushButton[nav="true"]:checked`
  - `QFrame#taskCard[prio="high"]`
- 勾选图标与下拉箭头在运行时用 QPainter 生成 PNG，再用 QSS `image:` 引用，避免外部资源
- 自绘图表每次 `paintEvent` 读取当前令牌，切换主题后自动重绘

### 5.2 主题切换

`theme.apply(app, mode)` 解析 `system/light/dark`：

- `system` 读取 `QStyleHints.colorScheme()`
- 重新设置 palette + stylesheet
- 自定义控件（卡片、表格前景色、图表）通过各页面的 `refresh/restyle` 重新取色

主题设置存 `settings` 表，下次启动恢复。

### 5.3 页面结构

`MainWindow`：

- 左侧固定导航 + `QStackedWidget`
- 页面：工作台 / 看板 / 仓库 / GitHub
- 菜单 / 快捷键 / 状态栏 / 窗口几何持久化
- 页面间信号路由：任务变化 → 工作台标脏；仓库扫描 → 刷新看板与 GitHub 选择列表
- 启动时同步 IDE 工作区（可关闭）、打开上次页面

## 6. 安全与隐私

- `.env` 在 `.gitignore` 中，绝不入库
- Token 用 Windows DPAPI（`CryptProtectData`，附加固定 entropy）加密，base64 后写入 `GITHUB_TOKEN_DPAPI`
- 读取顺序：DPAPI 密文 → 旧明文（自动迁移）→ 旧数据库值（自动迁移）
- 设置页不回显已保存 Token；留空保存表示不修改
- 非 Windows / DPAPI 失败：降级明文并记录一次告警
- 无遥测；网络仅 GitHub API + 用户配置的 git 远程
- 日志不含 Token；错误堆栈可能包含本地路径

## 7. 测试与验证

- `pytest`：20 个用例
  - schema 建表与 v1→v2 迁移、备份
  - 任务 CRUD、完成时间生命周期、筛选、排序
  - 统计、今日聚焦、完成趋势
  - 仓库扫描 / 状态 / 提交历史 / 工作区同步
  - DPAPI 往返、明文迁移、数据库旧值迁移
  - 设置对话框保存 / 留空 / 清除
  - 后台 Worker 回调送达、错误回调
  - 主窗口冒烟：四页导航、快速添加、主题切换
- 隔离方式：每个测试 `tmp_path`，monkeypatch `db.DB_PATH`、`backup.DB_PATH`、`settings.ENV_FILE`；UI 用 `QT_QPA_PLATFORM=offscreen`
- `scripts/screenshots.py` 使用 `PM_DATA_DIR` / `PM_ENV_FILE` / `PM_SYNC_WORKSPACE=0`，生成演示数据与 `docs/screenshots`
- `ruff check` 使用 `ruff.toml`（E4/E7/E9/F/I）

## 8. 关键文件

| 文件 | 职责 |
| --- | --- |
| `app/ui/theme.py` | 设计令牌、QSS、palette、运行时图标 |
| `app/ui/main_window.py` | 导航、菜单、快捷键、信号路由、主题应用 |
| `app/ui/tabs/dashboard_tab.py` | 统计卡、今日聚焦、趋势、仓库健康 |
| `app/ui/tabs/kanban_tab.py` | 筛选、快速添加、列、拖拽、右键菜单 |
| `app/ui/tabs/repos_tab.py` | 仓库表格、路径省略委托、终端/编辑器/pull |
| `app/ui/tabs/github_tab.py` | 概览、Issue/PR 列表与详情入口 |
| `app/core/workers.py` | QRunnable 生命周期与回调 |
| `app/core/db.py` / `backup.py` | schema / 迁移 / 备份 |
| `app/core/secrets.py` | DPAPI 加解密 |
| `app/services/task_service.py` | 任务 SQL 与完成时间维护 |
| `app/services/stats_service.py` | 工作台统计查询 |

## 9. 已知限制与后续方向

**限制**

- GitHub 列表 100 条 / 评论 50 条上限，未做分页 UI
- 无 commit / push / 创建 PR 的界面
- 看板列内顺序不持久化，只持久化状态
- 单窗口、单实例；不支持多设备同步
- 工作区同步会覆盖 `folders`（`settings` 保留）
- DPAPI 绑定 Windows 用户；换账户需重新填 Token
- 移除扫描根目录不会立即清理仍在磁盘上的仓库
- 无自动更新、无安装包（当前从源码运行）

**后续方向**

- PR 创建 / 本地 commit 与 push（需要更谨慎的写操作确认）
- 任务归档、重复任务、子任务
- 列表分页 / 搜索 API 化
- 看板列内排序与持久化
- PyInstaller 打包与签名
- 对非 Windows 平台的密钥存储（Keychain / Secret Service）
