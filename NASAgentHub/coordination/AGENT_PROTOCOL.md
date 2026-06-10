# AgentHub 文件协议 v0.1

## 目标

让 `微信直连codex`、`Codexapp1`、`Codexapp2`、`Codexapp3` 四个 Codex 对话通过同一套文件状态协作，而不是依赖聊天记忆互相猜。

## 角色

- `codex-main`：总控 PM，负责任务拆分、分配、验收、合并、发布决策。
- `codex-app1`：后端 / 自动化 / InfoRadar Core worker。
- `codex-app2`：前端 / Mana Hub / Cloudflare / Web 入口 worker。
- `codex-app3`：测试 / 文档 / 数据 / QA worker。

## 开工流程

1. 读取本协议和 5 个 coordination 文件。
2. 确认自己是谁，只领取 `owner_agent` 等于自己的任务。
3. 确认任务状态是 `queued` 或 `claimed`。
4. 在 `TASK_BOARD.json` 中登记 `in_progress`。
5. 在 `AGENT_STATUS.json` 中登记当前任务、workspace 和下一步。
6. 只在自己的 workspace 或 output 目录工作。

## 实时心跳规则

`AGENT_STATUS.json` 只代表登记状态，不代表 Codex 对话真实在线。

每个 agent 在启动、领取任务、完成任务、被用户唤醒时，必须刷新：

```bash
python shared/common_scripts/heartbeat_agent.py --agent-id codex-app2 --thread "微信直连Codexapp2" --note "正在处理前端任务"
```

网页只把 `coordination/AGENT_HEARTBEATS.json` 中最近 5 分钟内有心跳的 agent 显示为“实时在线”。

没有心跳或心跳过期时，只能显示为“未接入实时检查”或“心跳过期”，不能因为登记状态是 `active` 就宣称正在工作。

## 收工流程

1. 写结果报告到 `agents/<agent_id>/output/<task_id>.md`。
2. 更新任务状态为 `needs_review` 或 `done`。
3. 更新 `AGENT_STATUS.json`。
4. 追加事件到 `logs/EVENT_LOG.ndjson`。
5. 释放自己持有的锁。

## 锁规则

需要改这些地方时必须先登记 `LOCKS.json`：

- `shared/*`
- `projects/*/main`
- `coordination/PROJECT_REGISTRY.json`
- Cloudflare / systemd / OpenClaw 相关配置说明

没有锁时，只能读，不能写。

## 安全规则

禁止：

1. 暴露裸 shell、Cockpit、SSH、未认证端口。
2. 把 `WEB_ACCESS_TOKEN`、Cloudflare token、OpenAI API key 写进聊天或文档。
3. 未经任务授权修改 systemd、Cloudflare、OpenClaw、NAS 网络。
4. 在非自己 workspace 中批量改文件。
5. 直接删除项目主线文件。

## 验收规则

任务完成不等于聊天里说“完成”。必须至少满足：

1. 有结果文件。
2. 有状态更新。
3. 有事件日志。
4. 有验证说明。
5. 有风险说明。
