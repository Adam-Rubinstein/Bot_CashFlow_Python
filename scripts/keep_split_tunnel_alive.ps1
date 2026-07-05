param(
    # Как часто перепроверять туннель в постоянном режиме.
    [int]$CheckIntervalSeconds = 20
)

$ErrorActionPreference = "SilentlyContinue"

. (Join-Path $PSScriptRoot "split_tunnel_health.ps1")

$Root = if ($env:CASHFLOW_PROJECT_ROOT) { $env:CASHFLOW_PROJECT_ROOT } else { (Split-Path -Parent $PSScriptRoot) }
$StarterScript = Join-Path $Root "scripts\start_split_tunnel.ps1"
if (-not (Test-Path $StarterScript)) {
    throw "start_split_tunnel.ps1 not found. Set CASHFLOW_PROJECT_ROOT or restore the repo path."
}

$SshHost = if ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { "root@62.60.186.183" }
$RemoteProbeUrl = if ($env:CASHFLOW_REMOTE_PROBE_URL) { $env:CASHFLOW_REMOTE_PROBE_URL } else { "http://127.0.0.1:18080/" }
$PlinkHostKey = if ($env:CASHFLOW_PLINK_HOSTKEY) { $env:CASHFLOW_PLINK_HOSTKEY.Trim() } else { "SHA256:Bbpqi7aeMnjf4F+s4JpOlv/NoitFwXITg2ybMBJSpEY" }

$mutexName = "Global\BotCashFlowTunnelGuardian"
$mutex = $null
$createdNew = $false
try {
    $mutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$createdNew)
    if (-not $createdNew) {
        # Уже есть один guardian в этой Windows-сессии.
        return
    }

    Write-Host "Tunnel guardian started. Root: $Root. Interval: $CheckIntervalSeconds sec."
    while ($true) {
        try {
            $deployPw = $null
            if ($env:DEPLOY_SSH_PASSWORD -and $env:DEPLOY_SSH_PASSWORD.Trim().Length -gt 0) {
                $deployPw = $env:DEPLOY_SSH_PASSWORD.Trim()
            } else {
                $fromFile = Read-DotEnvKey (Join-Path $Root ".env") "DEPLOY_SSH_PASSWORD"
                if ($fromFile -and $fromFile.Trim().Length -gt 0) { $deployPw = $fromFile.Trim() }
            }
            if (-not (Test-SplitTunnelHealthy -SshHost $SshHost -RemoteProbeUrl $RemoteProbeUrl -DeployPw $deployPw -PlinkHostKey $PlinkHostKey -TimeoutSeconds 15)) {
                & $StarterScript -Force
            }
        } catch {
            # На всякий случай при неожиданной ошибке сразу пробуем поднять туннель вручную.
            & $StarterScript -Force
        }
        Start-Sleep -Seconds $CheckIntervalSeconds
    }
}
finally {
    if ($createdNew -and $mutex) {
        try { $mutex.ReleaseMutex() } catch {}
        $mutex.Dispose()
    }
}
