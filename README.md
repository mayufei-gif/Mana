# Mana

Mana 是当前域名 `https://inforadar.mana-mana.top` 的主线仓库，包含：

- `InfoRadar/`：InfoRadar Web、后端 API、前端页面、脚本与源池配置。
- `NASAgentHub/`：AgentHub 多 Codex 调度协议、任务板、角色状态、共享脚本和模板。
- `CourseMindNAS/`：NAS 视频字幕学习库源码，视频、转录产物、运行数据库和缓存不进入仓库。
- `tools/`：从旧运行目录导入、部署到 Ubuntu 的辅助脚本。

## 本地仓库位置

```text
G:\E盘\工作项目文件\Git Hub克隆仓库集群\Mana
```

## 日常工作副本

```text
G:\E盘\工作项目文件\NAS雷达\Mana
```

该目录是从主仓库建立的项目工作副本。后续 InfoRadar、Mana Hub、AgentHub、CourseMindNAS 的日常改动优先在这里完成；完成验证后再推送回 GitHub 主仓库 `mayufei-gif/Mana`。

## Ubuntu 运行位置

```text
/home/mana/InfoRadar
/home/mana/NASAgentHub
```

## CourseMind NAS 运行位置

```text
/home/yma648692gmail.com/coursemind-nas
```

CourseMind 的视频文件和处理产物只保存在 NAS；本仓库只保存可版本化源码。

## 主线发布流程

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
cd "G:\E盘\工作项目文件\Git Hub克隆仓库集群\Mana"
git status
git add .
git commit -m "update mana mainline"
git push origin main
.\tools\deploy_to_ubuntu.ps1
```

部署脚本会先在 Ubuntu 创建备份，再覆盖运行目录并重启 `inforadar-web.service` 对应进程。

## 从旧运行目录导入当前版本

如果还有其他 Codex 对话在旧工作目录修改：

```powershell
.\tools\import_live_sources.ps1
```

该脚本只导入可版本化源码，不导入 secrets、logs、data、reports、数据库和缓存。
