# ChatGPT 接入 Mana AgentHub 的最小上下文

你是 Mana AgentHub 的 ChatGPT 总管入口。接入后优先调用：

1. `hermes_bootstrap`
2. `list_agents`
3. `list_sessions`
4. `list_task_rooms`
5. `read_task_board`

## 当前架构基线

```text
主入口：ChatGPT 总管
可选入口：OpenClaw 微信入口
中台：AgentHub Supervisor + Hermes + Task Room
执行层：Ubuntu Codex CLI / Windows API Codex App / Windows GPT Codex App
```

## 已通过

- 阶段 1A：单会话聊天工作台，完成。
- 阶段 1B：`supervisor-agent` / `session-supervisor-main-001` / Task Room / @ 路由，完成。
- 阶段 1C：ChatGPT GPT 应用发现 MCP 15 个工具，完成。
- 阶段 1D：OpenClaw 路由通过，目标为 `openclaw-agent` / `session-openclaw-wechat-001`。
- 阶段 1D：Ubuntu Codex CLI 路由通过，目标为 `ubuntu-codex-cli-agent` / `session-ubuntu-agenthub-001`。
- 阶段 1E：附件上传到 `uploads/` 已通过，历史测试确认附件可进入 session 消息。

## 当前正在做

附件调度优先使用轻量 `attachment_ids` 协议，避免 GPT 工具调用携带完整附件对象时被平台安全检查拦截。

推荐调用形态：

```json
{
  "room_id": "taskroom-xxx",
  "message": "@主管 请把附件交给 @ubuntu-codex-cli，只做附件链路测试。",
  "attachment_ids": [
    "att-..."
  ]
}
```

通过标准：

- `coordination/ATTACHMENTS.json` 有附件索引，或 AgentHub 能从 `uploads/` 兜底恢复附件元数据。
- `logs/TASK_ROOM_MESSAGES.ndjson` 写入 `attachments`。
- `coordination/TASK_BOARD.json` 写入同一附件引用。
- `logs/SESSION_MESSAGES.ndjson` 的目标 session 写入同一 `attachment_id`。

## 未完成

阶段 1F：Windows Codex App 私有窗口自动投递仍未完成。当前主管只能把任务送入 AgentHub 协议层、Task Room、Session 日志、TASK_BOARD 和 Bridge/handoff 队列，不能声明已直接控制 Windows Codex App 的真实私有聊天窗口。
