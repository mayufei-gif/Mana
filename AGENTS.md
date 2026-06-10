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

1. 在本仓库修改源码。
2. 本地验证。
3. `git add` / `git commit` / `git push origin main`。
4. 运行 `tools/deploy_to_ubuntu.ps1`，将 Git 主线版本备份覆盖到 Ubuntu 运行目录。

如果其他对话仍在旧路径 `G:/E盘/工作项目文件/NAS/InfoRadar` 或 `G:/E盘/工作项目文件/NAS/NASAgentHub` 修改，合并进本仓库前先运行：

```powershell
tools/import_live_sources.ps1
```

