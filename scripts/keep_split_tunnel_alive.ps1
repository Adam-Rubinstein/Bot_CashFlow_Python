param(
    # Как часто перепроверять туннель в постоянном режиме (при Healthy).
    [int]$CheckIntervalSeconds = 20,
    # Максимальная пауза при VpsUnreachable (чтобы не долбить fail2ban/firewall).
    [int]$MaxUnreachableBackoffSeconds = 300
)

$ErrorActionPreference = "SilentlyContinue"

. (Join-Path $PSScriptRoot "split_tunnel_health.ps1")

$Root = if ($env:CASHFLOW_PROJECT_ROOT) { $env:CASHFLOW_PROJECT_ROOT } else { (Split-Path -Parent $PSScriptRoot) }
$StarterScript = Join-Path $Root "scripts\start_split_tunnel.ps1"
if (-not (Test-Path $StarterScript)) {
    throw "start_split_tunnel.ps1 not found. Set CASHFLOW_PROJECT_ROOT or restore the repo path."
}

$SshHost = if ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { "root@84.22.149.170" }
$RemoteProbeUrl = if ($env:CASHFLOW_REMOTE_PROBE_URL) { $env:CASHFLOW_REMOTE_PROBE_URL } else { "http://127.0.0.1:18080/" }
$PlinkHostKey = if ($env:CASHFLOW_PLINK_HOSTKEY) { $env:CASHFLOW_PLINK_HOSTKEY.Trim() } else { "SHA256:Bbpqi7aeMnjf4F+s4JpOlv/NoitFwXITg2ybMBJSpEY" }

$mutexName = "Global\BotCashFlowTunnelGuardian"
$mutex = $null
$createdNew = $false
$unreachableBackoff = $CheckIntervalSeconds
try {
    $mutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$createdNew)
    if (-not $createdNew) {
        # Уже есть один guardian в этой Windows-сессии.
        return
    }

    Write-Host "Tunnel guardian started. Root: $Root. Interval: $CheckIntervalSeconds sec."
    Write-SplitTunnelLog $Root "guardian started (interval=${CheckIntervalSeconds}s)"
    while ($true) {
        $sleepSec = $CheckIntervalSeconds
        try {
            $deployPw = $null
            if ($env:DEPLOY_SSH_PASSWORD -and $env:DEPLOY_SSH_PASSWORD.Trim().Length -gt 0) {
                $deployPw = $env:DEPLOY_SSH_PASSWORD.Trim()
            } else {
                $fromFile = Read-DotEnvKey (Join-Path $Root ".env") "DEPLOY_SSH_PASSWORD"
                if ($fromFile -and $fromFile.Trim().Length -gt 0) { $deployPw = $fromFile.Trim() }
            }

            $health = Get-SplitTunnelHealth -SshHost $SshHost -RemoteProbeUrl $RemoteProbeUrl -DeployPw $deployPw -PlinkHostKey $PlinkHostKey -TimeoutSeconds 15
            Write-SplitTunnelLog $Root ("status={0} code={1} detail={2}" -f $health.Status, $health.Code, $health.Detail)

            if ($health.Status -eq "Healthy") {
                $unreachableBackoff = $CheckIntervalSeconds
            } elseif ($health.Status -eq "VpsUnreachable") {
                # Не делать -Force: новые plink к закрытому :22 усугубляют fail2ban/бан IP.
                # Ensure без Force поднимет только локальный receiver при необходимости.
                & $StarterScript
                $sleepSec = $unreachableBackoff
                $unreachableBackoff = [Math]::Min($unreachableBackoff * 2, $MaxUnreachableBackoffSeconds)
                Write-Host "VPS SSH unreachable - skip Force, backoff ${sleepSec}s. $($health.Detail)"
            } else {
                # TunnelBroken: VPS:22 доступен, но reverse tunnel/receiver не отвечает 403.
                & $StarterScript -Force
                $unreachableBackoff = $CheckIntervalSeconds
                Write-Host "Tunnel broken - Force restart. $($health.Detail)"
            }
        } catch {
            Write-SplitTunnelLog $Root ("exception: {0}" -f $_.Exception.Message)
            # Неожиданная ошибка: Force только если VPS хотя бы пингуется по TCP:22.
            $hostName = Get-SshTargetHost $SshHost
            if (Test-TcpPortOpen -HostName $hostName -Port 22 -TimeoutMs 3000) {
                & $StarterScript -Force
            } else {
                & $StarterScript
                $sleepSec = $unreachableBackoff
                $unreachableBackoff = [Math]::Min($unreachableBackoff * 2, $MaxUnreachableBackoffSeconds)
            }
        }
        Start-Sleep -Seconds $sleepSec
    }
}
finally {
    if ($createdNew -and $mutex) {
        try { $mutex.ReleaseMutex() } catch {}
        $mutex.Dispose()
    }
}
