# T-DEMO-001 输出：AgentHub 使用说明草稿

## 结论

AgentHub 的第一版协作方式不是让 4 个 Codex 对话互相“读脑”，而是让它们共同读写同一套文件协议。

## 使用方式

1. 总控在 `TASK_BOARD.json` 创建任务。
2. 指定 `owner_agent`。
3. 对应 Codex 对话进入 `AgentHub` 目录。
4. 读取 `AGENTS.md` 和 `coordination/AGENT_PROTOCOL.md`。
5. 只在自己的 workspace 中工作。
6. 完成后写输出到 `agents/<agent_id>/output/`。
7. 总控验收并决定是否合并、发布或重启服务。

## 当前限制

1. 这不是自动多 agent 编排平台，仍需要人工启动各 Codex 对话。
2. 共享状态靠文件，不靠聊天记忆。
3. 正式发布仍由总控执行。

## 推荐下一步

把 `MH-P0-001` 分配给 `codex-app2`，让 Mana Hub 页面读取项目注册表和任务板。

