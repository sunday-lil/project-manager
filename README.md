# 项目管理器 (Project Manager)

本地 + GitHub 一体的桌面项目管理工具（PySide6）。

## 功能

- **任务看板**：待办 / 进行中 / 已完成三态拖拽流转，优先级、截止日、标签
- **本地仓库**：扫描工作区自动发现 git 仓库，查看分支 / ahead-behind / 脏状态 / 提交历史，一键 fetch
- **GitHub 集成**：Issues / Pull Requests 浏览、创建 Issue、评论、关开、合并 PR（Token 存于本地 `.env`，绝不上传）
- **工作区同步**：多扫描根目录管理，磁盘上已删除的仓库自动清理

## 运行

```bash
pip install -r requirements.txt
python main.py
```

首次使用在设置中填入 GitHub Token（[点此生成](https://github.com/settings/tokens)，需要 repo 权限）。Token 独立存放于项目根 `.env`，不入库。

## 技术栈

- Python 3.10+ / PySide6（界面）
- PyGithub（GitHub API，读操作带网络重试）
- GitPython（本地 git 仓库读取）
- SQLite（短连接 + 参数化 SQL）
- truststore（Windows 系统证书，解决 GitHub TLS 间歇失败）

## License

[MIT](LICENSE)
