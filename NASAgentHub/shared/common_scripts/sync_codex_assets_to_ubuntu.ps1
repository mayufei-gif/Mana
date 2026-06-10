param(
  [string]$Remote = "ubuntu-vm",
  [string]$RemoteHome = "/home/mana",
  [switch]$Execute
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

$localCodex = "C:/Users/asus/.codex"
$localAgents = "C:/Users/asus/.agents"

$includeCodexDirs = @(
  "skills",
  "rules",
  "memories",
  "plugins",
  "vendor_imports"
)

$includeCodexFiles = @(
  "AGENTS.md",
  "keybindings.json",
  "models_cache.json",
  "history.jsonl",
  "memories_1.sqlite",
  "goals_1.sqlite",
  ".codex-global-state.json"
)

$blocked = @(
  "auth.json",
  "cap_sid",
  ".sandbox-secrets",
  ".sandbox",
  ".sandbox-bin",
  ".tmp",
  "tmp",
  "sessions",
  "archived_sessions",
  "attachments",
  "computer-use",
  "process_manager",
  "logs_2.sqlite",
  "logs_2.sqlite-shm",
  "logs_2.sqlite-wal",
  "state_5.sqlite",
  "state_5.sqlite-shm",
  "state_5.sqlite-wal",
  "config.toml"
)

Write-Host "[codex-mirror] remote=$Remote"
Write-Host "[codex-mirror] execute=$($Execute.IsPresent)"
Write-Host "[codex-mirror] blocked assets are never copied:"
$blocked | ForEach-Object { Write-Host "  - $_" }

if (-not $Execute) {
  Write-Host ""
  Write-Host "[codex-mirror] dry run only. Re-run with -Execute to copy safe assets."
  Write-Host "[codex-mirror] this script never copies auth.json, cap_sid, .sandbox-secrets, config.toml, tokens, cookies, or API keys."
  exit 0
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stage = Join-Path $env:TEMP "codex_asset_mirror_$stamp"
$archive = Join-Path $env:TEMP "codex_asset_mirror_$stamp.tar.gz"

New-Item -ItemType Directory -Path $stage | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage ".codex") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage ".agents") | Out-Null

foreach ($dir in $includeCodexDirs) {
  $src = Join-Path $localCodex $dir
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $stage ".codex") -Recurse -Force
  }
}

foreach ($file in $includeCodexFiles) {
  $src = Join-Path $localCodex $file
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $stage ".codex") -Force
  }
}

$agentSkills = Join-Path $localAgents "skills"
if (Test-Path -LiteralPath $agentSkills) {
  Copy-Item -LiteralPath $agentSkills -Destination (Join-Path $stage ".agents") -Recurse -Force
}

$manifest = [ordered]@{
  created_at = (Get-Date).ToString("o")
  source_machine = $env:COMPUTERNAME
  copied_codex_dirs = $includeCodexDirs
  copied_codex_files = $includeCodexFiles
  copied_agents_dirs = @("skills")
  blocked = $blocked
  note = "No auth.json, cap_sid, .sandbox-secrets, config.toml, token, cookie, or API key is copied."
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stage "manifest.json") -Encoding UTF8

tar -czf $archive -C $stage .

ssh -o BatchMode=yes $Remote "mkdir -p '$RemoteHome/C/Users/asus' '$RemoteHome/C/D' '$RemoteHome/C/E' '$RemoteHome/C/G/E盘/工作项目文件/NAS' '$RemoteHome/.codex' '$RemoteHome/.agents' /tmp/codex_asset_mirror"
scp -o BatchMode=yes $archive "${Remote}:/tmp/codex_asset_mirror/codex_asset_mirror.tar.gz"
ssh -o BatchMode=yes $Remote @"
set -e
rm -rf /tmp/codex_asset_mirror/extracted
mkdir -p /tmp/codex_asset_mirror/extracted
tar -xzf /tmp/codex_asset_mirror/codex_asset_mirror.tar.gz -C /tmp/codex_asset_mirror/extracted
cp -a /tmp/codex_asset_mirror/extracted/.codex/. '$RemoteHome/.codex/'
cp -a /tmp/codex_asset_mirror/extracted/.agents/. '$RemoteHome/.agents/'
ln -sfn '$RemoteHome/.codex' '$RemoteHome/C/Users/asus/.codex'
ln -sfn '$RemoteHome/.agents' '$RemoteHome/C/Users/asus/.agents'
cp -f /tmp/codex_asset_mirror/extracted/manifest.json '$RemoteHome/.codex/asset_mirror_manifest.json'
echo CODEX_ASSET_MIRROR_OK
"@

Remove-Item -LiteralPath $stage -Recurse -Force
Remove-Item -LiteralPath $archive -Force

Write-Host "[codex-mirror] done"

