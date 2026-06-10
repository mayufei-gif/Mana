# Mana Hub 总控使用说明

## 一句话原则

所有 Codex 对话通过 `AgentHub/coordination` 了解全局状态，通过自己的 `agents/<agent_id>` 和 `workspaces/<task_id>-<agent_id>` 工作。

## 总控对话怎么分配任务

1. 在 `coordination/TASK_BOARD.json` 增加任务。
2. 指定 `owner_agent`。
3. 把任务 ID 发给对应对话。
4. 对方完成后，读取其输出文件验收。

## 子对话怎么接任务

进入 `G:\E盘\工作项目文件\NAS\NASAgentHub` 后，先读：

1. `AGENTS.md`
2. `coordination/AGENT_PROTOCOL.md`
3. 自己的 `agents/<agent_id>/AGENT.md`
4. `coordination/TASK_BOARD.json`

只接自己的任务，只改允许的路径。

## 文件边界

- 私有输出：`agents/<agent_id>/output`
- 私有工作区：`workspaces/<task_id>-<agent_id>`
- 共享资料：`shared`
- 正式主线：`projects/*/main`
- 全局状态：`coordination`

## 风险底线

不输出 token，不暴露裸 shell，不乱改 Cloudflare，不越权改主线。

