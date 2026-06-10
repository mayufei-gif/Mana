$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location "$Root/backend"

if (!(Test-Path "$Root/.venv/Scripts/python.exe")) {
    Set-Location $Root
    python -m venv .venv
    & "$Root/.venv/Scripts/python.exe" -m pip install -r "$Root/backend/requirements.txt"
    Set-Location "$Root/backend"
}

& "$Root/.venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
