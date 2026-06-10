$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ruleName = "InfoRadar Web 8769 LocalSubnet"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if (-not $existing) {
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 8769 `
        -RemoteAddress LocalSubnet `
        -Profile Any | Out-Null
}

Get-NetFirewallRule -DisplayName $ruleName |
    Select-Object DisplayName,Enabled,Profile,Direction,Action |
    Format-Table -AutoSize

Write-Host ""
Write-Host "InfoRadar firewall rule is ready. You can close this window."
Start-Sleep -Seconds 3
