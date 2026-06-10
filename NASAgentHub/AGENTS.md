# AgentHub 多 Codex 会话协作规则

本目录是多个 Codex 对话共享的个人 AI 公司式调度中枢。

任何对话进入本目录后，必须先读取：

1. `coordination/AGENT_PROTOCOL.md`
2. `coordination/PROJECT_REGISTRY.json`
3. `coordination/TASK_BOARD.json`
4. `coordination/AGENT_STATUS.json`
5. `coordination/LOCKS.json`

默认允许写入：

- `agents/<agent_id>/`
- `workspaces/<task_id>-<agent_id>/`
- `logs/EVENT_LOG.ndjson` 追加记录

默认禁止直接修改：

- `projects/*/main`
- 其他 agent 的 `agents/<agent_id>/`
- 其他任务的 `workspaces/`
- 明文 token、Cookie、API Key
- Cloudflare、systemd、OpenClaw、网络配置，除非任务明确授权

共享区 `shared/*` 必须先登记锁，再修改。

任何角色完成工作后，必须写结果报告到自己的 `agents/<agent_id>/output/`，并更新任务状态。

## NAS / Ubuntu 执行与多端去重规则

- 涉及 NAS、`nas-dxp`、Ubuntu 虚拟机、`ubuntu-vm`、OpenClaw、InfoRadar、Codex CLI runner 的命令，默认优先通过 SSH 免密执行；先验证 `ssh -o BatchMode=yes ubuntu-vm "echo SSH_KEY_OK"` 或 `ssh -o BatchMode=yes nas-dxp "echo SSH_KEY_OK"`。
- SSH 免密可用时，低风险检查和用户明确授权的部署/补丁步骤可以直接远程执行，不再要求用户进入远程桌面复制命令。
- sudo 必须单独验证：先执行 `sudo -n true`。如果失败，说明 sudo 仍需要密码；这时必须让用户本人在终端输入密码，不得猜测、记录、保存或回显密码。
- 微信指令、OpenClaw、Codex App、Codex CLI 之间必须通过 AgentHub 队列协调。任务领取以 `claim` / `dedupe_key` 为准，同一条指令不得被 Win11 和 Ubuntu 重复执行。
- 路由约定：`@ubuntu` / `@server` 交给 Ubuntu Codex CLI，`@win` / `@local` 交给 Win11 Codex App Bridge，`@any` 进入共享队列由可用 runner 认领。
- 需要共享的脚本、协议、任务板放在 `shared/` 或 `coordination/`；各 agent 的私有任务只写自己的 `agents/<agent_id>/` 和对应 `workspaces/<task_id>-<agent_id>/`。
