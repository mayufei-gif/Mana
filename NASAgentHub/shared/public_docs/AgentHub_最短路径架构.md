# AgentHub 最短路径架构

## 当前路径

```text
你
↓
codex-main 总控对话
↓
TASK_BOARD.json
↓
codex-app1 / codex-app2 / codex-app3
↓
各自 workspace
↓
output 报告
↓
codex-main 验收与发布
↓
Mana Hub 网页展示状态
```

## 为什么不用一上来就装复杂多 Agent 框架

因为当前四个 Codex App 侧栏对话不是天然共享记忆，也不能被外部稳定硬控。

最快可落地方式是：

```text
共享文件协议
+ 角色边界
+ 工作区隔离
+ 任务板
+ 状态板
+ 总控验收
```

后续如果需要自动化，再加：

1. SQLite。
2. FastAPI task API。
3. OpenClaw 微信投递。
4. Ubuntu systemd timer。
5. Cloudflare Access。

## 当前资源映射

| 资源 | 用途 |
|---|---|
| Codex App 四个对话 | 人工启动型 worker |
| Codex API key | 后续自动 worker，不放进文件 |
| OpenClaw | 微信任务投递入口 |
| Ubuntu VM | 长期运行中枢 |
| inforadar.mana-mana.top | 当前 Web 门户入口 |
| AgentHub 文件夹 | 共享事实源 |

