# Deploy bot_server.py to VPS and restart cashflow-bot-server.
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "split_tunnel_health.ps1")

$Root = Split-Path -Parent $PSScriptRoot
$SshHost = if ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { "root@62.60.186.183" }
$PlinkHostKey = if ($env:CASHFLOW_PLINK_HOSTKEY) { $env:CASHFLOW_PLINK_HOSTKEY.Trim() } else { "SHA256:Bbpqi7aeMnjf4F+s4JpOlv/NoitFwXITg2ybMBJSpEY" }

$deployPw = $null
if ($env:DEPLOY_SSH_PASSWORD -and $env:DEPLOY_SSH_PASSWORD.Trim().Length -gt 0) {
    $deployPw = $env:DEPLOY_SSH_PASSWORD.Trim()
} else {
    $fromFile = Read-DotEnvKey (Join-Path $Root ".env") "DEPLOY_SSH_PASSWORD"
    if ($fromFile -and $fromFile.Trim().Length -gt 0) { $deployPw = $fromFile.Trim() }
}
if (-not $deployPw) {
    throw "DEPLOY_SSH_PASSWORD not set in .env or environment."
}

$pscpCmd = Get-Command pscp.exe -ErrorAction SilentlyContinue
$plinkCmd = Get-Command plink.exe -ErrorAction SilentlyContinue
if (-not $pscpCmd -or -not $plinkCmd) {
    throw "pscp.exe / plink.exe not found in PATH (install PuTTY)."
}

$localFile = Join-Path $Root "bot_server.py"
$remotePath = "${SshHost}:/opt/app/bot-cashflow/bot_server.py"

& $pscpCmd.Source -batch -hostkey $PlinkHostKey -pw $deployPw $localFile $remotePath
if ($LASTEXITCODE -ne 0) { throw "pscp failed with exit code $LASTEXITCODE" }

$remoteCmd = "systemctl restart cashflow-bot-server && systemctl is-active cashflow-bot-server && grep _RECEIVER_MAX_ATTEMPTS /opt/app/bot-cashflow/bot_server.py | head -1"
& $plinkCmd.Source -ssh -batch -hostkey $PlinkHostKey -pw $deployPw $SshHost $remoteCmd
if ($LASTEXITCODE -ne 0) { throw "plink failed with exit code $LASTEXITCODE" }

Write-Host "Deploy OK: bot_server.py updated, cashflow-bot-server active."
