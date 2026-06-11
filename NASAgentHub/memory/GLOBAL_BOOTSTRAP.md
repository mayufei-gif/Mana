# Mana AI 公司总控系统 Bootstrap

Mana AgentHub 的定位是 AI 公司式总调度中枢，不是普通项目展示页。

核心链路：

ChatGPT 总管 Agent -> AgentHub MCP Server -> AgentHub Supervisor -> Hermes 长期记忆层 -> 下属 Agent / Codex 会话。

当前第一阶段目标：

1. GPT 应用通过 `https://inforadar.mana-mana.top/mcp` 接入 AgentHub。
2. GPT 能列出 Agent 和 Session。
3. GPT 能把消息写入指定 `session_id` 的任务和消息日志。
4. 网页和后续 Bridge 能从 `TASK_BOARD.json` 与 `SESSION_MESSAGES.ndjson` 读取同一份状态。

重要约束：

- Windows API Codex App Agent 是 Windows 主力 Agent。
- Windows API Codex App Agent 与 Windows GPT Codex App Agent 可以路径相同，但 agent_id、session_id、login_type 必须不同。
- 第一阶段不能假装已经能直接控制 Codex App 私有窗口；未绑定 app-server/thread_ref 时，消息状态必须是 `bridge-pending`。
