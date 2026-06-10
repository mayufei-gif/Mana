# NAS 部署说明

## 运行模式 A：Windows 本机运行，NAS 只存视频

适合当前阶段。Windows 负责运行后端、前端、FFmpeg 和 ASR/API 调用，NAS 只作为视频仓库。

`.env` 示例：

```text
NAS_VIDEO_DIR=Z:/网课视频
COURSEMIND_VIDEO_DIR=Z:/网课视频
COURSEMIND_STORAGE_DIR=./storage
AUTO_SCAN=true
AUTO_PROCESS_NEW_VIDEO=false
ASR_PROVIDER=mock
```

SMB 路径也支持：

```text
NAS_VIDEO_DIR=\\192.168.1.100\网课视频
COURSEMIND_VIDEO_DIR=\\192.168.1.100\网课视频
```

启动：

```powershell
./scripts/start-backend.ps1
./scripts/start-frontend.ps1
```

访问：

```text
http://127.0.0.1:3000
```

## 运行模式 B：NAS Docker

Docker Compose 会把视频目录、数据库目录、处理产物目录、日志目录、配置目录分别挂载为容器内固定路径：

```text
/videos     NAS 网课视频输入目录，只读
/videos_upload  长期上传入口，只读。建议对应电脑/手机单向同步到 NAS 的常用视频目录
/data       SQLite 数据库和系统数据
/processed  字幕、章节、笔记、音频缓存等处理产物
/logs       后端日志、任务日志、ASR 调用日志
/config     热词表、纠错表、模型配置等配置目录
```

### 在线构建模式

适合 NAS 能稳定访问 Docker Hub、Debian apt 源、npm registry 的情况。

```bash
docker compose up --build -d
```

### 离线镜像包模式

绿联 DXP4800 如果拉取 `node:24-alpine`、`python:3.12-slim`、`nginx:alpine` 超时，优先使用离线镜像包模式。NAS 端只做 `docker load` 和 `docker compose up`，不在宿主机安装 Python、Node、npm 或 FFmpeg。

在一台能正常访问 Docker Hub 的电脑或云服务器上执行：

```bash
bash scripts/build_offline_images.sh
```

把生成的镜像包同步到 NAS 项目目录，例如：

```text
CourseMind/images/coursemind_offline_images_20260603_013000.tar
```

然后在 NAS 终端执行：

```bash
sudo bash scripts/nas_load_offline_images.sh
```

或手动执行：

```bash
sudo docker load -i CourseMind/images/coursemind_offline_images_*.tar
sudo COMPOSE_FILE=docker-compose.offline.yml bash scripts/nas_verify.sh
```

离线模式使用 `docker-compose.offline.yml`，要求本地已经存在：

```text
coursemind-backend:offline
coursemind-frontend:offline
```

### 在线镜像仓库模式

如果有阿里云 ACR、腾讯云 TCR、华为云 SWR 或自建 Harbor，可以把 CourseMind 镜像推到在线仓库。NAS 端只需要能访问该仓库，不需要访问 Docker Hub。

构建机器上登录镜像仓库后执行：

```bash
export REGISTRY_PREFIX=registry.cn-hangzhou.aliyuncs.com/你的命名空间
bash scripts/build_push_registry_images.sh
```

NAS 上执行：

```bash
sudo docker login registry.cn-hangzhou.aliyuncs.com
export COURSEMIND_BACKEND_IMAGE=registry.cn-hangzhou.aliyuncs.com/你的命名空间/coursemind-backend:标签
export COURSEMIND_FRONTEND_IMAGE=registry.cn-hangzhou.aliyuncs.com/你的命名空间/coursemind-frontend:标签
sudo -E COMPOSE_FILE=docker-compose.registry.yml bash scripts/nas_verify.sh
```

注意：不要把镜像仓库密码、AccessKey 或 token 写进 `.env`、代码或任务书。终端登录即可，凭证由 Docker 自己保存。

### 绿联 DXP4800 本机低成本模式

DXP4800 已有 `ugreen/hermes-agent:v1` 时，可以直接复用该镜像运行 CourseMind。该镜像内已包含 Python、pip、Node、npm、FFmpeg，适合 Docker Hub 拉取失败但本地已有绿联镜像的场景。

```bash
sudo bash scripts/nas_verify_ugreen_local.sh
```

该模式使用：

```text
docker-compose.ugreen-local.yml
ugreen/hermes-agent:v1
```

后端依赖安装在 Docker volume `coursemind_backend_runtime`，前端工作目录安装在 Docker volume `coursemind_frontend_runtime`。源码目录只读挂载，避免容器把 Linux 版 `node_modules` 或 Python 缓存写回同步目录。

建议 `.env`：

```text
HOST_VIDEO_ROOT=/你的NAS真实路径/网课视频
HOST_UPLOAD_VIDEO_ROOT=/你的NAS真实路径/长期上传入口
HOST_DATA_DIR=/你的NAS真实路径/coursemind-data
HOST_PROCESSED_DIR=/你的NAS真实路径/coursemind-processed
HOST_LOG_DIR=/你的NAS真实路径/coursemind-logs
HOST_CONFIG_DIR=/你的NAS真实路径/coursemind-config
VIDEO_ROOT=/videos
VIDEO_ROOTS=/videos;/videos_upload
DATA_DIR=/data
PROCESSED_DIR=/processed
LOG_DIR=/logs
CONFIG_DIR=/config
DATABASE_URL=sqlite:////data/coursemind.db
AUTO_SCAN=true
AUTO_PROCESS_NEW_VIDEO=false
```

如果电脑本地常用上传目录是 `G:\E盘\NAS视频字幕`，NAS 端建议把它同步到一个独立真实目录，然后将 `HOST_UPLOAD_VIDEO_ROOT` 指向该 NAS 目录。CourseMind 容器内不直接识别 Windows 盘符，只识别挂载后的 `/videos_upload`。

注意：Docker 模式不要使用 Windows 盘符。容器内统一使用 Linux 路径。后端 Dockerfile 已安装并构建时验证 `ffmpeg -version`。

## 自动扫描和自动处理

推荐默认：

```text
AUTO_SCAN=true
SCAN_INTERVAL_SECONDS=300
SCAN_RECURSIVE=true
AUTO_PROCESS_NEW_VIDEO=false
AUTO_PROCESS_MAX_PER_ROUND=1
PROCESS_CONCURRENCY=1
```

这样新视频会自动出现在课程库，但不会自动调用收费 ASR/API。需要处理某个视频时，在课程库或处理页点击“优先处理”。

开启 `AUTO_PROCESS_NEW_VIDEO=true` 后，新视频会自动进入队列。建议配合：

```text
MAX_AUTO_PROCESS_MINUTES_PER_DAY=120
MAX_SINGLE_VIDEO_MINUTES=180
```

当前实现已支持单视频时长限制；每日总量限制配置已预留，后续可继续加强。

## 字幕化后才播放

当前产品规则：

```text
pending/queued/processing/failed/missing -> 不开放视频流
ready + subtitle_status=ready            -> 开放同步学习播放器
```

后端 `/api/videos/{video_id}/stream` 会校验状态。未完成字幕化处理时返回 `409`，避免前端或接口绕过直接播放裸视频。

## FunASR 配置

如果本地 FunASR 服务兼容 OpenAI `/audio/transcriptions`：

```text
ASR_PROVIDER=local_funasr
TRANSCRIPTION_BASE_URL=http://127.0.0.1:10095/v1
ASR_MODEL=funasr
TRANSCRIPTION_API_KEY=
```

如果部署在局域网机器上，把 `127.0.0.1` 换成对应 IP。前端不会暴露 `TRANSCRIPTION_API_KEY`。

## 阿里云百炼 DashScope ASR

真实字幕测试建议：

```text
ASR_PROVIDER=aliyun_dashscope
ASR_MODEL=fun-asr-realtime
DASHSCOPE_API_KEY=你的 DashScope Key
DASHSCOPE_WEBSOCKET_URL=wss://dashscope.aliyuncs.com/api-ws/v1/inference
AUTO_PROCESS_NEW_VIDEO=false
```

后续批量版计划接入：

```text
ASR_PROVIDER=aliyun_dashscope
ASR_MODEL=fun-asr
```

极致低成本备选：

```text
ASR_PROVIDER=aliyun_paraformer
ASR_MODEL=paraformer-v2
```

注意：当前 DashScope adapter 走 WebSocket Recognition 本地文件调用，真实闭环先用 `fun-asr-realtime`。`fun-asr` 和 `paraformer-v2` 是后续非实时批量 adapter 目标；当前 Paraformer 实时测试请用 `ASR_MODEL=paraformer-realtime-v2`。

所有 ASR provider 输出都会归一为：

```text
id / start / end / text / confidence
```

并兼容旧字段 `start_time/end_time`。

`ASR_PHRASE_ID` 可用于配置百炼热词 ID，旧配置名 `ASR_VOCABULARY_ID` 仍兼容。未知 `ASR_PROVIDER` 会让任务失败并暴露错误，不会静默使用 mock 占位字幕。

## 真实视频烟雾测试

启动后端后运行：

```powershell
./scripts/real-video-smoke.ps1 -VideoDir "G:/E盘/工作项目文件/NAS视频字幕/视频" -ApiBase "http://127.0.0.1:8000"
```

它会验证扫描、入队、ASR、字幕文件、章节、重点、状态变 `ready` 和 `/stream` gating。

## 常见问题

### 扫描不到视频

检查 `NAS_VIDEO_DIR` 或 `COURSEMIND_VIDEO_DIR` 是否存在，视频扩展名是否包含在 `VIDEO_EXTENSIONS` 中。

### 视频不能播放

这是当前设计：必须先处理到 `ready`，并生成智能字幕后才开放播放。去课程库点击“优先处理”。

### 字幕是占位文字

说明当前是 `TRANSCRIPTION_PROVIDER=mock`。它用于验证流程，不会产生真实字幕。切换 `openai`、`funasr` 或其它真实 provider 后重新处理。

### 处理失败

前端视频卡片和处理页会显示失败原因，也可查：

```text
storage/data/coursemind.db -> jobs.error_stage / jobs.error_message
```
