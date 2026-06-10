@echo off
chcp 65001 >nul
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python "%~dp0scripts\infobar_command.py" %*
exit /b %ERRORLEVEL%
