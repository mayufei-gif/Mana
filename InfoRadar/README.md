# InfoRadar

InfoRadar 是个人信息雷达系统的本地项目目录。

当前阶段：

- MVP-0 已实现：样例 Folo/RSS 数据导入、标题去重、分类评分、Excel/Markdown/微信摘要输出。
- MVP-1 已开始落地：Folo 输入目录、候选订阅源探测、正式源池、OPML 导入文件、微信指令映射。
- MVP-1C 已接入：统一命令入口、最新状态读取、候选源去重、无 RSS 但高价值官网监控表。
- MVP-1D 本地入口已接入：`run_inforadar.bat` / `run_inforadar.ps1`、自然命令别名、固定微信摘要、回传版 `latest_status.json`。
- MVP-2 已接入：真实 Folo 订阅源池、真实 RSS 抓取、`今日情报/今日政策/今日技术/今日AI` 表格生成。
- MVP-2.1 已接入：反馈记忆、兴趣权重文件、`今日AI` 别名修复、`深挖 第N条`、高风险软件资源识别、`latest_status.json` BOM 兼容读取、微信侧 v4/v5 补丁脚本更新。
- MVP-2.2 已接入：高风险软件资源强制降权、Folo 文件夹不再直接决定主分类、长期观察/低信号推广降权、短英文关键词边界匹配、RSS 抓取失败时缓存兜底。
- MVP-2.3 已接入：今日AI质量抽检、RSS源健康检查、源池治理建议、反馈细粒度权重影响排序。
- MVP-2.4 已接入：RSSHub实例配置、rsshub://解析、RSSHub备用候选、403源治理、URL异常标记降权、源池策略表回写。
- MVP-2.5 已接入：今日AI/政策/招聘/技术/证书/今日情报多主题生成、多主题质量抽检、主题源池治理报告、今日情报分组摘要。
- MVP-2.5B 已接入：全域信息雷达分类、全域候选源池扩展、全域命令入口、全域日报栏目、付费/平台/风险边界标记。
- MVP-2.6 已接入：全域候选源核验、Folo 可导入清单、OPML、人工核验清单、手动转发清单和禁用/风险源清单。
- MVP-2.7 已接入：Folo OPML 导入后源池状态 smoke test、全域情报导入后质量验收、`同步Folo全域源`、`Folo导入验收`、`全域情报验收`。
- MVP-2.8A 已接入：`收集 <内容>` 文本/链接入口、manual_inbox 原文保存、`source_trace_id`、`dedupe_key`、平台推断、`查看收集箱` 微信摘要。
- MVP-2.8B 已接入：`处理收集箱`、`查看收集结果`、manual_inbox 结构化分类、风险识别、价值等级、建议行动、`manual_collected_items_YYYYMMDD.xlsx/md/csv` 输出。

关键路径：

```text
项目根目录：G:\E盘\工作项目文件\NAS\InfoRadar
微信回传目录：G:\E盘\工作项目文件\NAS回传\FOLO
```

运行 MVP-0：

```powershell
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/inforadar_mvp.py" --topic "样例"
```

发现候选订阅源并探测 RSS/Atom：

```powershell
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/discover_sources.py" --probe --timeout 5
```

把可添加候选源整理成正式源池和 Folo 可导入 OPML：

```powershell
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/build_source_pool.py"
```

统一命令入口：

```powershell
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "推荐订阅源 电工证"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "生成源池"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "生成Folo表格 今日"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "今日AI"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "今日政策"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "今日招聘"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "今日技术"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "今日证书"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "今日情报"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "全域情报"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "扩展全域源池"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "核验全域源池"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "生成Folo导入清单"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "同步Folo全域源"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "Folo导入验收"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "全域情报验收"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "收集 学校 山西晋中理工学院奖学金通知 https://example.com"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "收集 购物 淘宝万用表链接 价格59 https://example.com"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "查看收集箱"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "处理收集箱"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "查看收集结果"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "我的学校"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "本地山西"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "时事热点"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "国际观察"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "科技前沿"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "开源动态"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "网络安全"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "法律权益"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "健康医学"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "财经商业"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "学习资源"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "购物情报"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "风险提醒"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "深挖 第1条"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "这个有用"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "治理RSS源"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "检查RSSHub"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "修复URL异常"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/audit_topic_reports.py"
python "G:/E盘/工作项目文件/NAS/InfoRadar/scripts/infobar_command.py" "查看最新结果"
```

微信/bridge 固定入口：

```powershell
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "今日情报"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "查源 电工证"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "抓取Folo更新 政策"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "今日AI"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "今日政策"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "今日招聘"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "今日技术"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "今日证书"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "今日情报"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "全域情报"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "扩展全域源池"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "核验全域源池"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "生成Folo导入清单"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "同步Folo全域源"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "Folo导入验收"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "全域情报验收"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "收集 学校 山西晋中理工学院奖学金通知 https://example.com"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "查看收集箱"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "处理收集箱"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "查看收集结果"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "法律权益"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "健康医学"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "网络安全"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "深挖 第1条"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "这个没用"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "治理RSS源"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "检查RSSHub"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "修复URL异常"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "最新结果"
& "G:/E盘/工作项目文件/NAS/InfoRadar/run_inforadar.bat" "做源池"
```

注意：

- 不要把 Folo token、Cookie、账号凭证写入项目文件或日志。
- 第一阶段只处理用户导出、手动放入或公开可订阅的数据。
- Folo 可导入的 OPML 固定生成到 `sources/opml/InfoRadar_source_pool.opml`，并复制一份到微信回传目录。
- `sources/source_watchlist.csv` / `sources/source_watchlist.xlsx` 用于保存“无 RSS 但值得监控”的官网源。
- `memory/feedback_log.jsonl` / `memory/preference_memory.jsonl` 保存微信或本地反馈。
- `config/interest_weights.yaml` 保存当前兴趣权重；反馈命令会轻量调整权重。
- `config/rsshub_instances.yaml` 保存 RSSHub primary/backups；`backup_examples` 只是示例，不会当作真实可用实例测试。
- `sources/source_pool_strategy.csv` / `sources/source_pool_strategy.xlsx` 保存当前源池抓取策略，策略包括 `direct_rss`、`rsshub_primary`、`rsshub_backup`、`official_page`、`replace_needed`、`disabled`、`cache_only`。
- 403 源不硬绕过登录、验证码、付费墙、访问控制或反爬限制；只能进入备用 RSSHub、自建 RSSHub、替换源、官网人工核验或废弃流程。
- `reports/deep_research/` 保存 `深挖 第N条` 生成的完整报告；回传目录会保存一份同名 Markdown 和微信摘要。
- 固定摘要写入 `G:\E盘\工作项目文件\NAS回传\FOLO\latest_status_微信摘要.txt`。
- 最新状态同时写入项目内部 `logs/latest_status.json` 和回传目录 `G:\E盘\工作项目文件\NAS回传\FOLO\latest_status.json`。
- 反馈命令只记录对上一条任务的评价，不覆盖 `latest_status.json` 的业务结果。
- MVP-2.5 验收显示：AI、政策、今日情报已有有效输出；招聘、工业技术、证书主题当前主要缺口是 Folo 源池覆盖不足，不应靠放宽分类硬凑内容。
- MVP-2.5B 以后系统定位从职业/专业雷达扩展为全域情报雷达，但候选源不等于已导入 Folo；新增源必须先人工核验质量和边界，再逐步加入 Folo/RSS/监控源池。
- MVP-2.6 输出的 `all_domain_folo_import_ready.opml` 只包含可公开订阅的 RSS/Atom 源；`manual_review`、`manual_forward`、`watch_only`、`disabled` 不会写入 OPML。
- MVP-2.7 验收显示：OPML 4 个可导入源中当前 Folo 源池检测到 3 个，`Hacker News` 尚未检测到；全域情报基础质量通过，但 OPML 源暂未贡献条目，导入/刷新后需复测。
- MVP-2.8A 只做文本/链接收集，不做截图、OCR、附件解析；收集内容写入 `data/manual_inbox/wechat/manual_items_YYYYMMDD.jsonl`，原文保存到 `data/manual_inbox/wechat/raw/`。
- MVP-2.8B 采用 processed 索引，不回写原始收集记录；重复 `dedupe_key` 不会重复处理，结构化结果写入 `data/manual_inbox/processed/manual_processed_YYYYMMDD.jsonl` 和回传目录表格。
- MVP-2.8C 已将 `manual_collected_items` 接入全域情报输入源；`全域情报` 会合并 Folo/RSS 和手动收集内容，`今日情报` 会排除 `是否进入今日情报=no` 的购物类内容，`我的学校`、`购物情报`、`付费资源`、`风险提醒` 可按栏目单独生成表格。
- 手动收集内容进入全域表时会保留 `source_trace_id`、`dedupe_key`、`用户备注`、`原始内容保存路径`、`是否进入今日情报`、`是否进入长期知识库`，方便追踪来源和后续处理。
- MVP-3.1 已新增自由指令调度器：`/ir <自然语言>`、`/find <自然语言>` 会先查本地资料，再按需进入候选源发现；`/watch <关键词>` 会写入 `sources/watch_only_requests.csv`；`/collect`、`/deep` 复用已有收集和深挖脚本。
- 自由指令第一版采用规则解析，不直接让模型调用工具；模型配置预留在 `config/agent_config.yaml`，后续可接 DashScope/OpenAI/local，但工具调用仍走白名单和边界规则。
- 封闭平台、购物平台和付费知识只处理公开线索或元信息；禁止绕过登录、验证码、付费墙、DRM、平台反爬或访问控制。
