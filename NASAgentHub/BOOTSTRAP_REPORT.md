# AgentHub Bootstrap Report

时间：2026-06-05

## 已创建

- `AGENTS.md`
- `coordination/AGENT_PROTOCOL.md`
- `coordination/PROJECT_REGISTRY.json`
- `coordination/TASK_BOARD.json`
- `coordination/AGENT_STATUS.json`
- `coordination/LOCKS.json`
- `coordination/MERGE_REQUESTS.json`
- `coordination/INBOX.ndjson`
- `logs/EVENT_LOG.ndjson`
- `agents/codex-main/AGENT.md`
- `agents/codex-app1/AGENT.md`
- `agents/codex-app2/AGENT.md`
- `agents/codex-app3/AGENT.md`
- `shared/templates/*`
- `shared/public_docs/ManaHub_总控使用说明.md`

## 已注册项目

- `AgentHub`
- `InfoRadar`
- `ManaHubWeb`
- `OpenClawBridge`
- `UbuntuCodex`

## 已登记任务

- `T-DEMO-001`：已完成，用于证明文件协议可运行。
- `MH-P0-001`：待 `codex-app2` 处理，升级 Mana Hub 页面读取项目注册表和任务板。
- `MH-P0-002`：待 `codex-app1` 处理，规划 OpenClaw 微信任务投递格式。

## 当前仍是占位

1. 还没有真正的自动锁管理脚本。
2. 还没有 API / SQLite 任务服务。
3. 还没有把 AgentHub 同步到 `/srv/agenthub`。
4. 还没有把 Mana Hub 页面接到 `PROJECT_REGISTRY.json` 和 `TASK_BOARD.json`。
5. 其他 Codex 对话还没有逐个进入 AgentHub 读取协议并报到。

## 下一步

1. 让 4 个对话分别读取自己的 `AGENT.md`。
2. 先跑 `MH-P0-001` 和 `MH-P0-002`。
3. 做一个只读状态 API，让网页显示项目注册表和任务板。
4. 再迁移到 Ubuntu `/srv/agenthub`。

