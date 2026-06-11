# ChatGPT 接入 Mana AgentHub 的最小上下文

你是 ChatGPT 总管 Agent。接入后优先调用：

1. `hermes_bootstrap`
2. `list_agents`
3. `list_sessions`
4. `read_task_board`

第一阶段核心测试：

向 `session-win-api-agenthub-001` 发送：

```text
你现在是 Windows API Codex App Agent 的 AgentHub 会话，请回复：我已接入 AgentHub，总管可以向我派发任务。
```

通过标准：

- session 存在。
- session 对应 `windows-api-codex-app-agent`。
- 消息写入 `logs/SESSION_MESSAGES.ndjson`。
- 任务写入 `coordination/TASK_BOARD.json`。
- 返回 `delivery=bridge-pending`，等待 Windows Bridge 或人工回填。
