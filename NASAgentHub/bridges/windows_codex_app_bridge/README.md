# Windows Codex App Bridge

这个 Bridge 是 AgentHub 到 Windows Codex App 会话的第一阶段投递器。

当前能力：

- 通过 HTTPS 读取 AgentHub 中 `delivery=bridge-pending` 的 session 消息。
- 为每条消息生成一个 handoff Markdown 文件。
- 把远端消息标记为 `status=handoff-ready`、`delivery=manual-handoff`。
- 支持把 Codex App 的人工回复回填到 `SESSION_MESSAGES.ndjson`。

当前不会做的事：

- 不做鼠标键盘盲投递。
- 不假装已经能控制 Codex App 私有窗口。
- 在没有 Codex App app-server/thread API 前，不会自动把消息发进具体聊天窗口。

## 使用方式

先配置 MCP URL。不要把 token 提交进 Git。

```powershell
$env:AGENTHUB_SERVER_URL = "https://inforadar.mana-mana.top/mcp?access_token=<AgentHub token>"
```

检查状态：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" status
```

拉取待投递消息并生成 handoff：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" poll --session-id "session-win-api-agenthub-001"
```

持续轮询：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" poll --watch --poll-seconds 5
```

Codex App 回复后回填：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" reply --session-id "session-win-api-agenthub-001" --in-reply-to "<message_id>" --task-id "<task_id>" --file "reply.txt"
```

## 后续升级

拿到 Codex App app-server/thread API 后，把 `poll` 中的 `write_handoff` 替换为真实 `send_message(thread_ref, content)`，并把状态标记为 `delivery=codex-app-thread`。
