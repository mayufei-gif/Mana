param(
  [int]$IntervalSeconds = 15
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

$AgentHubRoot = "G:\E盘\工作项目文件\NAS\NASAgentHub"
$MonitorScript = Join-Path $AgentHubRoot "shared\common_scripts\codex_app_monitor.py"
$CoordinationDir = Join-Path $AgentHubRoot "coordination"
$ThreadsJson = Join-Path $CoordinationDir "CODEX_APP_THREADS.json"
$HeartbeatsJson = Join-Path $CoordinationDir "AGENT_HEARTBEATS.json"
$LogDir = Join-Path $AgentHubRoot "logs"
$LogPath = Join-Path $LogDir "codex_app_monitor_watch.log"
$RemoteCoordination = "ubuntu-vm:/home/mana/NASAgentHub/coordination/"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

while ($true) {
  try {
    python $MonitorScript --agenthub-root $AgentHubRoot --max-messages 6 | Out-Null
    scp $ThreadsJson $HeartbeatsJson $RemoteCoordination | Out-Null
    "$(Get-Date -Format o) synced codex app threads" | Out-File -FilePath $LogPath -Encoding utf8 -Append
  } catch {
    "$(Get-Date -Format o) ERROR $($_.Exception.Message)" | Out-File -FilePath $LogPath -Encoding utf8 -Append
  }
  Start-Sleep -Seconds ([Math]::Max(5, $IntervalSeconds))
}
