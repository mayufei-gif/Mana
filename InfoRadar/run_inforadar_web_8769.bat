@echo off
chcp 65001 >nul
cd /d "G:\E盘\工作项目文件\NAS\InfoRadar"
python -m uvicorn web.backend.app:app --host 0.0.0.0 --port 8769
