# AgentHub

AgentHub 是 Mana AI 公司总控系统本体，负责 Agent 注册、Session 注册、任务队列、MCP 工具、Hermes 记忆层、输出与验收中心。

当前正式架构基线：

```text
主入口：ChatGPT 总管
可选入口：OpenClaw 微信入口
中台：AgentHub Supervisor + Hermes + Task Room
执行层：Ubuntu Codex CLI / Windows API Codex App / Windows GPT Codex App
```

当前阶段重点已经从单 session 消息写入推进到 ChatGPT 主入口下的多 Agent 调度协议：

- `supervisor-agent` 已登记，主管会话为 `session-supervisor-main-001`。
- Task Room 协议已新增，任务房间登记在 `coordination/TASK_ROOMS.json`，消息写入 `logs/TASK_ROOM_MESSAGES.ndjson`。
- @ 路由已新增，支持 `@主管`、`@openclaw`、`@windows-api-codex`、`@windows-gpt-codex`、`@ubuntu-codex-cli` 和 `@session-*`。
- 附件协议已新增，附件存储在 `uploads/`，消息通过 `attachments` 引用；`attachment_ids` 轻量调度已通过，GPT 只传 `attachment_id`，由 AgentHub 服务端展开附件元数据。
- MCP 工具应暴露 `list_task_rooms`、`create_task_room`、`send_task_room_message`、`supervisor_dispatch` 和 `upload_attachment`。

已通过的 GPT MCP 端到端验收：

1. ChatGPT GPT 应用已发现 MCP 15 个工具。
2. Task Room 创建通过。
3. `@主管` 调度 `@openclaw` 通过：`assigned_agent=openclaw-agent`、`assigned_session=session-openclaw-wechat-001`。
4. `@主管` 调度 `@ubuntu-codex-cli` 通过：`assigned_agent=ubuntu-codex-cli-agent`、`assigned_session=session-ubuntu-agenthub-001`。
5. 附件上传到 `uploads/` 通过；历史测试确认附件可进入目标 session 消息。
6. `attachment_ids` 轻量附件调度通过：Task Room、TASK_BOARD 和目标 Ubuntu session 消息均能写入同一 `attachment_id`。

下一步：

1. 单独研究阶段 1F：Windows Codex App 私有窗口自动投递。
2. 优先寻找 Codex App app-server/thread API 和可稳定定位文件夹/会话的接口；继续避免脆弱鼠标键盘自动化。

真实状态边界：`GPT -> MCP -> AgentHub -> Task Room / Session / Queue` 已进入验证阶段；`Windows Bridge -> Codex App 私有 thread 自动投递` 仍未完成，不能对外宣称已经控制真实 Codex App 聊天窗口。
