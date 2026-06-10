param(
  [string]$InfoRadarSource = "G:\E盘\工作项目文件\NAS\InfoRadar",
  [string]$AgentHubSource = "G:\E盘\工作项目文件\NAS\NASAgentHub"
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$InfoRadarTarget = Join-Path $RepoRoot "InfoRadar"
$AgentHubTarget = Join-Path $RepoRoot "NASAgentHub"

if (!(Test-Path -LiteralPath $InfoRadarSource)) {
  throw "InfoRadar source not found: $InfoRadarSource"
}
if (!(Test-Path -LiteralPath $AgentHubSource)) {
  throw "AgentHub source not found: $AgentHubSource"
}

New-Item -ItemType Directory -Force -Path $InfoRadarTarget, $AgentHubTarget | Out-Null

Copy-Item -LiteralPath `
  (Join-Path $InfoRadarSource "README.md"), `
  (Join-Path $InfoRadarSource "run_inforadar.bat"), `
  (Join-Path $InfoRadarSource "run_inforadar.ps1"), `
  (Join-Path $InfoRadarSource "run_inforadar_web.bat"), `
  (Join-Path $InfoRadarSource "run_inforadar_web_8769.bat") `
  -Destination $InfoRadarTarget -Force

robocopy (Join-Path $InfoRadarSource "web") (Join-Path $InfoRadarTarget "web") /MIR /XD __pycache__ /XF *.pyc *.bak* /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy (Join-Path $InfoRadarSource "scripts") (Join-Path $InfoRadarTarget "scripts") /MIR /XD __pycache__ /XF *.pyc *.bak* /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy (Join-Path $InfoRadarSource "config") (Join-Path $InfoRadarTarget "config") /MIR /XD __pycache__ /XF *.pyc *.bak* *.env *token* *secret* *cookie* /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy (Join-Path $InfoRadarSource "sources") (Join-Path $InfoRadarTarget "sources") /MIR /XD __pycache__ /XF *.pyc *.bak* *token* *secret* *cookie* /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null

Copy-Item -LiteralPath `
  (Join-Path $AgentHubSource "AGENTS.md"), `
  (Join-Path $AgentHubSource "README.md"), `
  (Join-Path $AgentHubSource "BOOTSTRAP_REPORT.md") `
  -Destination $AgentHubTarget -Force

robocopy (Join-Path $AgentHubSource "coordination") (Join-Path $AgentHubTarget "coordination") /MIR /XF *.sqlite *.db *.bak* *token* *secret* *cookie* /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy (Join-Path $AgentHubSource "shared") (Join-Path $AgentHubTarget "shared") /MIR /XD __pycache__ /XF *.pyc *.bak* *token* *secret* *cookie* /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
robocopy (Join-Path $AgentHubSource "agents") (Join-Path $AgentHubTarget "agents") /MIR /XD __pycache__ /XF *.pyc *.bak* *token* *secret* *cookie* /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null

Write-Host "Imported live sources into $RepoRoot"

