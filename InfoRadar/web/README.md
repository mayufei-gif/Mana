# InfoRadar 移动端 Web 控制台

这是 InfoRadar 的移动端优先 Web 外壳。它不重写情报逻辑，只通过白名单调用：

```powershell
python scripts/infobar_command.py "<command>"
```

## 目录

```text
web/
  backend/
    app.py
    command_runner.py
    file_index.py
    schemas.py
  frontend/
    index.html
    app.js
    style.css
```

## 安装依赖

当前机器如果没有 `fastapi` 和 `uvicorn`，先安装：

```powershell
pip install -r "G:\E盘\工作项目文件\NAS\InfoRadar\web\requirements.txt"
```

## 启动

```powershell
cd /d "G:\E盘\工作项目文件\NAS\InfoRadar"
python -m uvicorn web.backend.app:app --host 0.0.0.0 --port 8768
```

也可以运行：

```powershell
G:\E盘\工作项目文件\NAS\InfoRadar\run_inforadar_web.bat
```

如果 8768 已被其他服务占用，可运行当前环境使用的 8769 启动脚本：

```powershell
G:\E盘\工作项目文件\NAS\InfoRadar\run_inforadar_web_8769.bat
```

## 访问

本机：

```text
http://127.0.0.1:8768
```

局域网：

```text
http://Windows-IP:8768
```

Tailscale：

```text
http://Windows-Tailscale-IP:8768
```

当前实测端口为：

```text
http://100.85.194.78:8769
```

## API

- `GET /api/health`
- `POST /api/command`
- `GET /api/latest`
- `GET /api/files`
- `GET /api/file?path=xxx`
- `GET /api/manual-inbox`
- `GET /api/watch`
- `GET /api/source-pool`

## 安全边界

- Web 端只允许调用白名单命令。
- 后端不接受任意 shell 命令。
- 文件读取限制在 `G:\E盘\工作项目文件\NAS回传\FOLO`。
- 前端不展示 API Key、bridge token、Folo token 或 Cookie。
- 可通过环境变量 `WEB_ACCESS_TOKEN` 开启简单访问口令。

设置口令示例：

```powershell
$env:WEB_ACCESS_TOKEN="你的本地访问口令"
python -m uvicorn web.backend.app:app --host 0.0.0.0 --port 8768
```
