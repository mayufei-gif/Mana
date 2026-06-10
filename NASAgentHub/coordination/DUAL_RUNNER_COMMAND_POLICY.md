# Win11 / Ubuntu 双端指令执行协议 v0.1

## 目标

让本地 Win11 和 NAS Ubuntu 都能响应微信 `/codexapp*` 指令，但同一条微信指令只能被一个端执行。

这件事不能靠“谁登录了哪个账号”解决。正确模型是：

```text
微信指令
  -> 统一队列
  -> 生成 command_id / dedupe_key
  -> Win11 与 Ubuntu worker 竞争认领
  -> 只有认领成功的一端执行
  -> 另一端看到已认领/已完成，直接跳过
```

## 角色

- `win11-api-runner`：本地电脑 Codex App，适合使用 API Key 或本地 GUI 能力。
- `win11-account-runner`：本地电脑 Codex App，适合使用已登录账号的 GUI 能力。
- `ubuntu-account-runner`：Ubuntu 上的 Codex CLI/App 会话，适合 24 小时在线、执行 NAS 项目和服务端任务。
- `supervisor`：你或 `codex-main`，负责任务分配、验收和决定 `hold` 指令是否放行。

账号登录态不是任务归属。任务归属由队列字段决定。

## 冲突解决

如果 Win11 登录 API Key，Ubuntu 登录你的账号，不会天然冲突；真正会冲突的是 OpenClaw 同时把同一条消息发给两个 worker。

解决方式：

1. OpenClaw 不再直接广播执行。
2. OpenClaw 先把微信消息写入统一队列。
3. 每条消息生成稳定 `command_id`。
4. Win11 和 Ubuntu 都轮询队列。
5. worker 执行前必须原子认领。
6. 认领失败的一端不得执行，只能记录 `skip_already_claimed`。

## 指令策略

`now`：

- 进入队列，但优先级最高。
- 仍然需要认领，不能绕过队列直接执行。

`queue`：

- 普通排队执行。
- 适合不打断当前 Codex 会话。

`hold`：

- 写入队列但状态为 `held`。
- 需要 supervisor 手动 `approve` 后才能被 worker 认领。

## 路由策略

默认：

```text
target_runner = any
```

这表示 Win11 / Ubuntu 谁先认领谁执行。

可选显式路由：

```text
@win      -> target_runner = win11
@ubuntu   -> target_runner = ubuntu
@local    -> target_runner = win11
@server   -> target_runner = ubuntu
```

显式路由仍然要经过队列和认领，不允许直接执行。

## 去重字段

统一队列必须保存：

- `command_id`
- `dedupe_key`
- `source`
- `external_msg_id`
- `raw_text`
- `policy`
- `target_runner`
- `status`
- `claimed_by`
- `lease_expires_at`

推荐生成规则：

```text
dedupe_key = sha256(source + external_msg_id + normalized_text)
command_id = cmd_ + sha256(dedupe_key)[:24]
```

如果微信平台能提供稳定 `msg_id`，优先使用它；没有时使用文本、群名、发送人、分钟级时间窗口组合。

## 原子认领

认领必须使用数据库事务或等价的原子锁。

推荐 SQLite：

```sql
BEGIN IMMEDIATE;
UPDATE commands
SET status='claimed', claimed_by=?, lease_expires_at=?
WHERE command_id=? AND status='queued';
COMMIT;
```

只有 `UPDATE` 影响 1 行时，worker 才能执行。

## 失败恢复

- `lease_expires_at` 过期后，任务可重新回到 `queued`。
- worker 执行失败后写 `failed`，不得无限重试。
- 重试需要递增 `attempt_count`。
- 同一 `dedupe_key` 的已完成任务不得再次执行。

## Codex 资产迁移边界

允许镜像：

- `C:/Users/asus/.codex/skills`
- `C:/Users/asus/.agents/skills`
- `C:/Users/asus/.codex/rules`
- `C:/Users/asus/.codex/memories`
- `C:/Users/asus/.codex/plugins`
- `C:/Users/asus/.codex/vendor_imports`
- `C:/Users/asus/.codex/AGENTS.md`
- `C:/Users/asus/.codex/keybindings.json`
- `C:/Users/asus/.codex/models_cache.json`
- `C:/Users/asus/.codex/history.jsonl`
- `C:/Users/asus/.codex/memories_1.sqlite`
- `C:/Users/asus/.codex/goals_1.sqlite`

禁止直接镜像：

- `auth.json`
- `cap_sid`
- `.sandbox-secrets`
- API Key
- Cookie
- ChatGPT/OpenAI 桌面登录态
- Cloudflare token
- TOTP secret
- 任何明文凭证

Ubuntu 必须自己登录账号；Win11 的登录态不搬家。

## Ubuntu 路径映射

实际运行路径：

```text
Ubuntu Codex: /home/mana/.codex
Ubuntu agents: /home/mana/.agents
项目主目录: /home/mana/NASAgentHub, /home/mana/InfoRadar
```

为了缓解 Windows 路径差异，建立兼容映射：

```text
C:/Users/asus/.codex
  -> /home/mana/C/Users/asus/.codex
  -> symlink to /home/mana/.codex

C:/Users/asus/.agents
  -> /home/mana/C/Users/asus/.agents
  -> symlink to /home/mana/.agents

G:/E盘/工作项目文件/NAS
  -> /home/mana/C/G/E盘/工作项目文件/NAS
```

不建议在 Linux 根目录硬建 `/C`、`/D`、`/E`，因为需要 sudo 且会污染系统根目录。先在 `/home/mana/C` 下建立兼容盘符。

## 当前推荐架构

```text
OpenClaw Weixin
  -> enqueue command
  -> COMMAND_QUEUE.sqlite on Ubuntu
  -> win11-api-runner poll/claim
  -> ubuntu-account-runner poll/claim
  -> exactly one runner executes
  -> result writes back to queue + WeChat
```

这条路径最短，而且能解释、能恢复、能扩展。

