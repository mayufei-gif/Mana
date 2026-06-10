# CourseMind NAS

CourseMind NAS 是面向 NAS 网课视频的本地学习助手。当前目标不是普通播放器，而是把 NAS 目录里的视频自动变成“字幕、章节、重点、笔记、搜索、进度定位”都同步的学习资料。

核心流程：

```text
视频放入 NAS 指定目录
  -> 后端自动扫描入库
  -> 队列提取音频、切片、转录、清洗字幕、生成智能字幕
  -> 生成章节、重点时间轴、Markdown 笔记
  -> 状态 ready 后开放同步学习播放器
```

为保证学习体验，当前版本要求视频先完成字幕化和知识化处理，才允许正式播放。未完成时页面显示处理状态、进度、失败原因和“优先处理/重新处理”按钮。

## 当前能力

- FastAPI 后端、React + TypeScript 前端、SQLite 数据库。
- 自动扫描 NAS 视频目录，支持中文路径、空格路径、递归扫描和扩展名配置。
- 缺失或移动的视频会标记为 `missing`，不直接删除数据库记录。
- 内置单并发处理队列，支持手动处理、优先处理、重新处理。
- 处理状态细化：`pending / queued / extracting_audio / splitting_audio / transcribing / optimizing_subtitle / generating_chapters / generating_highlights / generating_note / indexing / ready / failed / missing`。
- 保存 `raw_transcript.json`、`clean_transcript.json`、`smart_subtitle.vtt`、`smart_subtitle.srt`。
- 播放器加载智能字幕，支持字幕、章节、重点点击跳转和上次播放位置恢复。
- 搜索标题、文件夹、字幕、重点和笔记。
- ASR provider 架构已拆分：`mock`、`openai`、`local_funasr/funasr`、`aliyun_dashscope` 可切换，`aliyun_paraformer` 作为 DashScope 兼容别名。
- ASR 输出统一为 `id/start/end/text/confidence`，并兼容旧的 `start_time/end_time` 字段。

## Windows 本机 + NAS 映射盘

1. 复制配置：

```powershell
Copy-Item ".env.example" ".env"
```

2. 编辑 `.env`：

```text
NAS_VIDEO_DIR=Z:/网课视频
COURSEMIND_VIDEO_DIR=Z:/网课视频
AUTO_SCAN=true
AUTO_PROCESS_NEW_VIDEO=false
ASR_PROVIDER=mock
```

也可以使用 SMB 路径：

```text
NAS_VIDEO_DIR=\\192.168.1.100\网课视频
COURSEMIND_VIDEO_DIR=\\192.168.1.100\网课视频
```

3. 启动后端：

```powershell
./scripts/start-backend.ps1
```

4. 启动前端：

```powershell
./scripts/start-frontend.ps1
```

5. 打开：

```text
http://127.0.0.1:3000
```

## 使用方式

1. 把视频放入 `NAS_VIDEO_DIR`。
2. 等自动扫描，或在课程库点击“立即扫描”。
3. 新视频默认只入库，不会自动调用收费接口。
4. 点击“优先处理”开始字幕化处理。
5. 状态变为 `ready` 后点击“打开学习”。
6. 在播放器中查看视频、智能字幕、章节、重点时间轴和笔记。

## 避免 API 费用失控

默认配置：

```text
AUTO_PROCESS_NEW_VIDEO=false
AUTO_PROCESS_MAX_PER_ROUND=1
PROCESS_CONCURRENCY=1
MAX_SINGLE_VIDEO_MINUTES=180
```

开启 `AUTO_PROCESS_NEW_VIDEO=true` 后，新视频会自动进入处理队列，可能调用真实 ASR 或 AI 接口并产生费用。建议先用 `TRANSCRIPTION_PROVIDER=mock` 跑通流程，再切换真实 provider。

## 阿里云百炼 DashScope ASR

当前真实字幕测试建议优先使用 `fun-asr-realtime`：

```text
ASR_PROVIDER=aliyun_dashscope
ASR_MODEL=fun-asr-realtime
DASHSCOPE_API_KEY=你的 DashScope Key
DASHSCOPE_WEBSOCKET_URL=wss://dashscope.aliyuncs.com/api-ws/v1/inference
AUTO_PROCESS_NEW_VIDEO=false
AUDIO_CHUNK_SECONDS=600
```

`ASR_PHRASE_ID` 可填写百炼热词 ID；旧配置名 `ASR_VOCABULARY_ID` 仍兼容。未知 `ASR_PROVIDER` 会直接失败并记录 `error_stage=transcribing`，不会静默回退到 mock。

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

注意：当前代码里的 DashScope adapter 走 WebSocket Recognition 本地文件调用，真实闭环先用 `fun-asr-realtime`。`fun-asr` 和 `paraformer-v2` 属于后续非实时批量 adapter 目标，当前不要直接作为闭环测试配置；如需 Paraformer 实时测试，用 `ASR_PROVIDER=aliyun_paraformer`、`ASR_MODEL=paraformer-realtime-v2`。

API Key 只放后端 `.env`，不要写进前端。

## FunASR / 本地 ASR

如果本地或局域网 FunASR 服务提供 OpenAI-compatible `/audio/transcriptions` 接口，可以这样配置：

```text
ASR_PROVIDER=local_funasr
TRANSCRIPTION_BASE_URL=http://127.0.0.1:10095/v1
ASR_MODEL=funasr
TRANSCRIPTION_API_KEY=
```

如果服务需要鉴权，把 key 写入 `TRANSCRIPTION_API_KEY`。前端不会接触 API Key。

## OpenAI-compatible ASR

```text
ASR_PROVIDER=openai
OPENAI_API_KEY=你的 Key
OPENAI_BASE_URL=https://api.openai.com/v1
TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
```

兼容服务只要实现 `/audio/transcriptions`，也可以通过 `OPENAI_BASE_URL` 或 `TRANSCRIPTION_BASE_URL` 接入。

## Docker / NAS 部署

绿联 DXP4800 如果 Docker Hub 拉取超时，优先使用离线镜像包方式。NAS 端只执行 `docker load` 和 `docker compose up`，不需要在 NAS 宿主机安装 Python、Node、npm 或 FFmpeg。

### 方式 A：NAS 可直接访问 Docker Hub

```powershell
Copy-Item ".env.example" ".env"
docker compose up --build
```

### 方式 B：NAS 不能稳定访问 Docker Hub

在一台能正常访问 Docker Hub 的电脑或云服务器上执行：

```bash
bash scripts/build_offline_images.sh
```

把生成的 `CourseMind/images/coursemind_offline_images_*.tar` 同步到 NAS 项目目录后，在 NAS 终端执行：

```bash
sudo bash scripts/nas_load_offline_images.sh
```

离线模式使用 `docker-compose.offline.yml`，镜像名固定为：

```text
coursemind-backend:offline
coursemind-frontend:offline
```

### 方式 C：在线镜像仓库

如果你有阿里云 ACR、腾讯云 TCR、华为云 SWR 或自建 Harbor，可以把镜像推到在线仓库，让 NAS 直接拉自己的 CourseMind 镜像。

在构建机器上登录镜像仓库后执行：

```bash
export REGISTRY_PREFIX=registry.cn-hangzhou.aliyuncs.com/你的命名空间
bash scripts/build_push_registry_images.sh
```

脚本会输出 `COURSEMIND_BACKEND_IMAGE` 和 `COURSEMIND_FRONTEND_IMAGE`。在 NAS 上设置这两个变量后运行：

```bash
sudo docker login registry.cn-hangzhou.aliyuncs.com
export COURSEMIND_BACKEND_IMAGE=registry.cn-hangzhou.aliyuncs.com/你的命名空间/coursemind-backend:标签
export COURSEMIND_FRONTEND_IMAGE=registry.cn-hangzhou.aliyuncs.com/你的命名空间/coursemind-frontend:标签
sudo -E COMPOSE_FILE=docker-compose.registry.yml bash scripts/nas_verify.sh
```

### 方式 D：绿联 DXP4800 低成本本机模式

如果 NAS 已有 `ugreen/hermes-agent:v1`，可以直接复用它作为 CourseMind 运行底座，避免拉取 Docker Hub 的 `python/node/nginx` 基础镜像。

```bash
sudo bash scripts/nas_verify_ugreen_local.sh
```

该模式会在容器内使用国内源安装 Python/npm 依赖：

```text
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
```

Docker 内部建议使用：

```text
VIDEO_ROOT=/videos
VIDEO_ROOTS=/videos;/videos_upload
DATA_DIR=/data
PROCESSED_DIR=/processed
LOG_DIR=/logs
CONFIG_DIR=/config
DATABASE_URL=sqlite:////data/coursemind.db
```

在 `.env` 中配置宿主机挂载目录：

```text
HOST_VIDEO_ROOT=/你的NAS真实路径/网课视频
HOST_UPLOAD_VIDEO_ROOT=/你的NAS真实路径/长期上传入口
HOST_DATA_DIR=/你的NAS真实路径/coursemind-data
HOST_PROCESSED_DIR=/你的NAS真实路径/coursemind-processed
HOST_LOG_DIR=/你的NAS真实路径/coursemind-logs
HOST_CONFIG_DIR=/你的NAS真实路径/coursemind-config
```

容器内固定挂载为 `/videos`、`/videos_upload`、`/data`、`/processed`、`/logs`、`/config`。后端默认同时扫描 `/videos` 和 `/videos_upload`，其中 `/videos_upload` 建议留给手机/电脑单向上传到 NAS 的长期课程入口。后端 Dockerfile 会安装并验证 `ffmpeg -version`。

## 真实视频烟雾测试

先启动后端和前端，再运行：

```powershell
./scripts/real-video-smoke.ps1 -VideoDir "G:/E盘/工作项目文件/NAS视频字幕/视频" -ApiBase "http://127.0.0.1:8000"
```

它会依次验证：扫描入库、优先处理、ASR、`raw_transcript.json`、`clean_transcript.json`、`smart_subtitle.vtt/srt`、章节、重点、`ready` 状态和 `/stream` gating。

## 关键目录

```text
backend/app/services/scanner_service.py              NAS 扫描
backend/app/services/queue_service.py                后台扫描和处理队列
backend/app/services/transcription/                  ASR provider
backend/app/workers/video_worker.py                  视频处理流水线
backend/app/services/subtitle_service.py             字幕清洗和导出
frontend/src/main.tsx                                课程库、处理页、播放器
storage/                                             数据库、字幕、音频缓存、笔记
```
