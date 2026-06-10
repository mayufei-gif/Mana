param(
  [string]$SshTarget = "ubuntu-vm",
  [string]$RemoteBase = "/home/mana",
  [switch]$AllowDirty
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archive = Join-Path $env:TEMP "mana_deploy_$stamp.tar.gz"
$archiveName = Split-Path -Leaf $archive
$remoteScriptLocal = Join-Path $env:TEMP "mana_remote_deploy_$stamp.sh"
$remoteScriptName = Split-Path -Leaf $remoteScriptLocal

if (!(Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
  throw "Not a git repository: $RepoRoot"
}

$dirty = git -C $RepoRoot status --porcelain
if ($dirty -and !$AllowDirty) {
  throw "Working tree is dirty. Commit/push first, or rerun with -AllowDirty."
}

tar -czf $archive `
  --exclude ".git" `
  --exclude "__pycache__" `
  --exclude "*.pyc" `
  --exclude "*.bak*" `
  --exclude ".env" `
  --exclude ".env.*" `
  --exclude "*token*" `
  --exclude "*secret*" `
  --exclude "*cookie*" `
  --exclude "InfoRadar/data" `
  --exclude "InfoRadar/logs" `
  --exclude "InfoRadar/reports" `
  --exclude "InfoRadar/memory" `
  --exclude "NASAgentHub/logs" `
  --exclude "NASAgentHub/secrets" `
  --exclude "NASAgentHub/previews" `
  --exclude "NASAgentHub/workspaces" `
  -C $RepoRoot InfoRadar NASAgentHub README.md AGENTS.md .gitignore tools
scp -T $archive "${SshTarget}:/tmp/$archiveName"

$remoteScript = @'
set -e
STAMP="__STAMP__"
REMOTE_BASE="__REMOTE_BASE__"
ARCHIVE="/tmp/__ARCHIVE_NAME__"
RELEASE_ROOT="/tmp/mana-release-$STAMP"
BACKUP_ROOT="$REMOTE_BASE/backups/mana-deploy/$STAMP"

rm -rf "$RELEASE_ROOT"
mkdir -p "$RELEASE_ROOT" "$BACKUP_ROOT"
tar -xzf "$ARCHIVE" -C "$RELEASE_ROOT"

mkdir -p "$REMOTE_BASE/InfoRadar" "$REMOTE_BASE/NASAgentHub"

for path in \
  "$REMOTE_BASE/InfoRadar/web" \
  "$REMOTE_BASE/InfoRadar/scripts" \
  "$REMOTE_BASE/InfoRadar/config" \
  "$REMOTE_BASE/InfoRadar/sources" \
  "$REMOTE_BASE/NASAgentHub/coordination" \
  "$REMOTE_BASE/NASAgentHub/shared" \
  "$REMOTE_BASE/NASAgentHub/agents"; do
  if [ -e "$path" ]; then
    mkdir -p "$BACKUP_ROOT$(dirname "${path#$REMOTE_BASE}")"
    cp -a "$path" "$BACKUP_ROOT/${path#$REMOTE_BASE/}"
  fi
done

cp -a "$RELEASE_ROOT/InfoRadar/." "$REMOTE_BASE/InfoRadar/"
cp -a "$RELEASE_ROOT/NASAgentHub/." "$REMOTE_BASE/NASAgentHub/"

MAIN_PID=$(systemctl show inforadar-web.service --property=MainPID --value 2>/dev/null || echo 0)
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
  kill "$MAIN_PID" || true
  sleep 5
fi

echo "DEPLOYED_BACKUP=$BACKUP_ROOT"
systemctl is-active inforadar-web.service 2>/dev/null || true
systemctl show inforadar-web.service --property=MainPID --value 2>/dev/null || true
'@

$remoteScript = $remoteScript.Replace("__STAMP__", $stamp).Replace("__REMOTE_BASE__", $RemoteBase).Replace("__ARCHIVE_NAME__", $archiveName)

$utf8NoBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($remoteScriptLocal, $remoteScript, $utf8NoBom)
scp -T $remoteScriptLocal "${SshTarget}:/tmp/$remoteScriptName"
$remoteExec = "bash /tmp/$remoteScriptName; status=`$?; rm -f /tmp/$remoteScriptName; exit `$status"
ssh -o BatchMode=yes $SshTarget $remoteExec
Remove-Item -LiteralPath $archive -Force
Remove-Item -LiteralPath $remoteScriptLocal -Force
