# Mana 仓库协作规则

本仓库是 `https://inforadar.mana-mana.top` 当前 Mana AI / InfoRadar / AgentHub 网站的主线源码仓库。

## 工作原则

- 默认所有网页、后端、AgentHub 调度台相关改动，都应优先在本仓库完成。
- 不要从旧备份覆盖 `InfoRadar/web/frontend/style.css`、`app.js`、`index.html`。
- 修改项目卡片样式时，必须保留状态胶囊居中规则：
  - `.project-top { align-items: flex-start; }`
  - `.status-chip, .status-pill { display: inline-grid; place-items: center; min-height: 32px; line-height: 1; }`
- 不提交 token、Cookie、API Key、TOTP secret、Cloudflare tunnel token、账号登录态。
- 运行数据、日志、生成报告、数据库和队列文件不进入 Git 主线。

## 标准流程

1. 先在本地拉取主仓库最新版本：`git fetch origin main`，确认无冲突后 `git pull --ff-only`。
2. 只在本仓库对应项目目录里修改源码：
   - `InfoRadar/`：主站、登录、项目入口、InfoRadar 后端和前端。
   - `NASAgentHub/`：AgentHub 调度协议、任务板、角色状态和共享脚本。
   - `CourseMindNAS/`：CourseMind NAS 视频字幕学习库源码。
3. 修改前后都检查 `git status --short`，不要把其他对话正在写的无关文件混进同一次提交。
4. 本地验证通过后再提交：`git add` / `git commit` / `git push origin main`。
5. 只有推送到主仓库成功后，才运行 `tools/deploy_to_ubuntu.ps1`，将 Git 主线版本备份覆盖到 Ubuntu 网站运行目录。

## 网站可见功能部署规则

- 如果改动会影响浏览器里能看到的页面、按钮、项目入口、接口返回、登录状态或项目详情页，提交推送后必须立即部署到 Ubuntu。
- 部署后必须验证对应项目入口，而不是只验证首页：
  - InfoRadar：验证 `https://inforadar.mana-mana.top/#inforadar` 或相关 API。
  - AgentHub：验证 `https://inforadar.mana-mana.top/#agenthub`。
  - OpenClaw：验证 `https://inforadar.mana-mana.top/#openclaw`。
  - CourseMind：验证 `https://inforadar.mana-mana.top/coursemind/`。
- 验证通过后，最终回复要明确写出：最新 commit、是否已 push、是否已 deploy、验证过的 URL 和 HTTP 状态。
- 只有纯文档、规则说明、不会影响网页运行的仓库维护改动，才可以只 push 不 deploy。

## 多 Codex 对话同步规则

- 每个 Codex 对话开始工作前，都必须先同步 `origin/main`，不要基于过期本地文件直接改。
- 如果另一个对话仍在同步或写入，先等远端 `main` 稳定，再继续提交和部署。
- 一个对话只负责一个明确项目目录；跨项目共享内容放在同级共享目录或 `NASAgentHub/` 协调文件中。
- 需要新增功能时，先把缺失功能合进本地 `Mana` 仓库，再推送到 GitHub 主仓库。
- 不要直接把旧运行目录、`.venv`、备份目录、视频、数据库、缓存、NAS 回传结果或密钥文件整体复制进主线。
- 如果必须从旧运行目录吸收改动，只导入可版本化源码，并在提交前做敏感信息扫描和差异检查。

如果其他对话仍在旧路径 `G:/E盘/工作项目文件/NAS/InfoRadar` 或 `G:/E盘/工作项目文件/NAS/NASAgentHub` 修改，合并进本仓库前先运行：

```powershell
tools/import_live_sources.ps1
```
