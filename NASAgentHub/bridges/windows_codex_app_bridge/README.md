# Windows Codex App Bridge

这个 Bridge 是 AgentHub 到 Windows Codex App 会话的第一阶段投递器。

当前能力：

- 通过 HTTPS 读取 AgentHub 中 `delivery=bridge-pending` 的 session 消息。
- 为每条消息生成一个 handoff Markdown 文件，默认固定写入：
  `G:\E盘\工作项目文件\Git Hub克隆仓库集群\Mana\NASAgentHub\bridges\windows_codex_app_bridge\outbox`
- 把远端消息标记为 `status=handoff-ready`、`delivery=manual-handoff`。
- 把 handoff 文件内容同步写回 AgentHub 消息的 `handoff_content`，让网页可以直接复制。
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

如果当前脚本不是从 Mana 仓库内运行，必须显式指定稳定 outbox：

```powershell
python "G:\E盘\工作项目文件\Git Hub克隆仓库集群\Mana\NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" poll --session-id "session-win-api-agenthub-001" --outbox "G:\E盘\工作项目文件\Git Hub克隆仓库集群\Mana\NASAgentHub\bridges\windows_codex_app_bridge\outbox"
```

持续轮询：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" poll --watch --poll-seconds 5
```

Codex App 回复后回填：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" reply --session-id "session-win-api-agenthub-001" --in-reply-to "<message_id>" --task-id "<task_id>" --file "reply.txt"
```

## 状态语义

- `bridge-pending`：AgentHub 已写入消息队列，等待 Windows Bridge 拉取。
- `handoff-ready` / `manual-handoff`：Bridge 已生成 handoff，尚未真实投递到 Codex App 私有会话。
- `manual-copied`：用户已在网页复制 handoff，准备人工粘贴到对应 Codex App 会话。
- `codex-replied` / `manual-reply`：用户或 Bridge 已把 Codex App 回复回填到 AgentHub。
- `app-server-delivered`：未来真实绑定 Codex App `thread_ref` 后，消息已通过 app-server 投递。
- `app-server-replied`：未来通过 app-server 读取到真实 Codex 回复。

## 阶段 1F 只读发现与 dry-run

生成真实 Codex App thread 树和候选绑定：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" discover-thread-tree
```

默认只扫描并绑定 `G:\E盘\工作项目文件\NAS\微信直连codex` 这个 Codex App 文件夹里的对话。需要临时切换目标时，可设置：

```powershell
$env:CODEX_APP_TARGET_WORKSPACE = "G:\E盘\工作项目文件\NAS\微信直连codex"
```

输出文件：

- `coordination/CODEX_APP_THREAD_TREE.json`
- `coordination/CODEX_APP_THREAD_BINDINGS.json`

查看当前本机投递能力：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" capabilities
```

只做 dry-run，不真实投递：

```powershell
python "NASAgentHub\bridges\windows_codex_app_bridge\bridge.py" dry-run-send --session-id "session-win-api-agenthub-001" --thread-ref "<thread_id>" --message "测试消息"
```

注意：

- 自动发现的绑定只能是 `candidate`，用户确认前不能改成 `active`。
- 当前绑定粒度优先是 `folder_candidate`：列出该文件夹里的 `candidate_threads`，由用户明确选择 `thread_ref` 后再做 dry-run。
- 如果 `delivery_method` 是 `app-ipc-pipe` 但 `app_ipc_protocol_known=false`，只能说明 IPC 管道有线索，不能写入用户消息。
- `send-real-test` 必须带 `--confirm`，且当前协议未知时会拒绝真实投递。

## 后续升级

拿到 Codex App app-server/thread API 后，把 `poll` 中的 `write_handoff` 替换为真实 `send_message(thread_ref, content)`，并把状态标记为 `status=app-server-delivered`、`delivery=app-server-delivered`。读取到回复后再标记 `app-server-replied`。
