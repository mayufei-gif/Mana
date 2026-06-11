# AgentHub

AgentHub 是 Mana AI 公司总控系统本体，负责 Agent 注册、Session 注册、任务队列、MCP 工具、Hermes 记忆层、输出与验收中心。

当前阶段重点已经从单 session 消息写入推进到多 Agent 调度协议：

- `supervisor-agent` 已登记，主管会话为 `session-supervisor-main-001`。
- Task Room 协议已新增，任务房间登记在 `coordination/TASK_ROOMS.json`，消息写入 `logs/TASK_ROOM_MESSAGES.ndjson`。
- @ 路由已新增，支持 `@主管`、`@openclaw`、`@windows-api-codex`、`@windows-gpt-codex`、`@ubuntu-codex-cli` 和 `@session-*`。
- 附件协议已新增，附件存储在 `uploads/`，消息通过 `attachments` 引用。
- MCP 工具应暴露 `list_task_rooms`、`create_task_room`、`send_task_room_message`、`supervisor_dispatch` 和 `upload_attachment`。

下一步不是继续加 UI，而是做 GPT MCP 端到端验收：

1. 通过 `/mcp` `tools/list` 确认新工具可见。
2. 通过 MCP 创建 `测试主管调度 OpenClaw` Task Room。
3. 在 Task Room 中通过 `@主管` 调度 `@openclaw`，确认 `assigned_agent=openclaw-agent`、`assigned_session=session-openclaw-wechat-001`。
4. 上传 `test.txt`，在 Task Room 中把附件调度给 `@ubuntu-codex-cli`，确认 `uploads/`、`TASK_ROOM_MESSAGES.ndjson` 和 `SESSION_MESSAGES.ndjson` 都有同一附件引用。

真实状态边界：`GPT -> MCP -> AgentHub -> Task Room / Session / Queue` 已进入验证阶段；`Windows Bridge -> Codex App 私有 thread 自动投递` 仍未完成，不能对外宣称已经控制真实 Codex App 聊天窗口。
