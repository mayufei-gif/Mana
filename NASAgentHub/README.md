# AgentHub：Mana 的个人 AI 公司式多项目中枢

## 当前定位

AgentHub 不是另一个普通项目，而是多个 Codex 对话共享的“公司制度 + 任务板 + 状态板 + 工作区”。

它解决的问题：

1. 四个 Codex 对话互相不知道对方在干什么。
2. 多项目并行时容易互相覆盖文件。
3. 你需要像主管一样分配任务、验收产物、统一发布。
4. 共享内容需要放在所有项目同级目录，而不是塞进某个项目里。

## 当前目录

Windows 源目录：

```text
G:\E盘\工作项目文件\NAS\NASAgentHub
```

Ubuntu 同步目录：

```text
/home/mana/NASAgentHub
```

公网入口：

```text
https://inforadar.mana-mana.top/
```

## 四个 Codex 对话角色

| 对话 | Agent ID | 角色 |
|---|---|---|
| 微信直连codex | `codex-main` | 主管 / PM / 调度 / 验收 / 发布 |
| 微信直连Codexapp1 | `codex-app1` | 后端 / 自动化 / InfoRadar Core / OpenClaw |
| 微信直连Codexapp2 | `codex-app2` | 前端 / Mana Hub Web / Cloudflare / Ubuntu 入口 |
| 微信直连Codexapp3 | `codex-app3` | 测试 / 文档 / 数据 / QA |

## 每个对话怎么协作

每个对话都必须通过这些文件了解全局：

```text
coordination/AGENT_PROTOCOL.md
coordination/PROJECT_REGISTRY.json
coordination/TASK_BOARD.json
coordination/AGENT_STATUS.json
coordination/LOCKS.json
logs/EVENT_LOG.ndjson
```

每个对话只能在自己的地方工作：

```text
agents/<agent_id>/
workspaces/<task_id>-<agent_id>/
```

共享文件放这里：

```text
shared/
```

正式项目主线放这里：

```text
projects/*/main
```

默认不允许子对话直接改正式主线。

## 当前第一批任务

已登记：

1. `T-DEMO-001`：Demo 文档任务，已完成。
2. `MH-P0-001`：Mana Hub 页面读取项目注册表和任务板，分配给 `codex-app2`。
3. `MH-P0-002`：OpenClaw 微信任务投递格式设计，分配给 `codex-app1`。

## 主管使用方式

你以后只需要在主对话里说：

```text
给 codex-app2 分配 MH-P0-001
验收 codex-app1 的 MH-P0-002
汇总所有 agent 状态
发布 Mana Hub
```

主对话再去读写 `TASK_BOARD.json`、`AGENT_STATUS.json`、`EVENT_LOG.ndjson`。

## 安全底线

禁止：

1. 暴露裸 shell。
2. 暴露 Cockpit。
3. 输出 token、Cookie、API Key。
4. 未授权改 Cloudflare / systemd / OpenClaw。
5. 子对话绕过任务板直接改其他项目。

