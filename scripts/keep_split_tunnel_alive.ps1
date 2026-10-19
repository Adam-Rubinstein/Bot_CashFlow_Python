param(
    # РљР°Рє С‡Р°СЃС‚Рѕ РїРµСЂРµРїСЂРѕРІРµСЂСЏС‚СЊ С‚СѓРЅРЅРµР»СЊ РІ РїРѕСЃС‚РѕСЏРЅРЅРѕРј СЂРµР¶РёРјРµ (РїСЂРё Healthy).
    [int]$CheckIntervalSeconds = 20,
    # РњР°РєСЃРёРјР°Р»СЊРЅР°СЏ РїР°СѓР·Р° РїСЂРё VpsUnreachable (С‡С‚РѕР±С‹ РЅРµ РґРѕР»Р±РёС‚СЊ fail2ban/firewall).
    [int]$MaxUnreachableBackoffSeconds = 300
)

$ErrorActionPreference = "SilentlyContinue"

. (Join-Path $PSScriptRoot "split_tunnel_health.ps1")

$Root = if ($env:CASHFLOW_PROJECT_ROOT) { $env:CASHFLOW_PROJECT_ROOT } else { (Split-Path -Parent $PSScriptRoot) }
$StarterScript = Join-Path $Root "scripts\start_split_tunnel.ps1"
if (-not (Test-Path $StarterScript)) {
    throw "start_split_tunnel.ps1 not found. Set CASHFLOW_PROJECT_ROOT or restore the repo path."
}

$SshHost = if ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { (Get-VpsSshHost) }
$RemoteProbeUrl = if ($env:CASHFLOW_REMOTE_PROBE_URL) { $env:CASHFLOW_REMOTE_PROBE_URL } else { "http://127.0.0.1:18080/" }
$PlinkHostKey = if ($env:CASHFLOW_PLINK_HOSTKEY) { $env:CASHFLOW_PLINK_HOSTKEY.Trim() } else { "SHA256:Bbpqi7aeMnjf4F+s4JpOlv/NoitFwXITg2ybMBJSpEY" }

$mutexName = "Global\BotCashFlowTunnelGuardian"
$mutex = $null
$createdNew = $false
$unreachableBackoff = $CheckIntervalSeconds
try {
    $mutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$createdNew)
    if (-not $createdNew) {
        # РЈР¶Рµ РµСЃС‚СЊ РѕРґРёРЅ guardian РІ СЌС‚РѕР№ Windows-СЃРµСЃСЃРёРё.
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
                # РќРµ РґРµР»Р°С‚СЊ -Force: РЅРѕРІС‹Рµ plink Рє Р·Р°РєСЂС‹С‚РѕРјСѓ :22 СѓСЃСѓРіСѓР±Р»СЏСЋС‚ fail2ban/Р±Р°РЅ IP.
                # Ensure Р±РµР· Force РїРѕРґРЅРёРјРµС‚ С‚РѕР»СЊРєРѕ Р»РѕРєР°Р»СЊРЅС‹Р№ receiver РїСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё.
                & $StarterScript
                $sleepSec = $unreachableBackoff
                $unreachableBackoff = [Math]::Min($unreachableBackoff * 2, $MaxUnreachableBackoffSeconds)
                Write-Host "VPS SSH unreachable - skip Force, backoff ${sleepSec}s. $($health.Detail)"
            } else {
                # TunnelBroken: VPS:22 РґРѕСЃС‚СѓРїРµРЅ, РЅРѕ reverse tunnel/receiver РЅРµ РѕС‚РІРµС‡Р°РµС‚ 403.
                & $StarterScript -Force
                $unreachableBackoff = $CheckIntervalSeconds
                Write-Host "Tunnel broken - Force restart. $($health.Detail)"
            }
        } catch {
            Write-SplitTunnelLog $Root ("exception: {0}" -f $_.Exception.Message)
            # РќРµРѕР¶РёРґР°РЅРЅР°СЏ РѕС€РёР±РєР°: Force С‚РѕР»СЊРєРѕ РµСЃР»Рё VPS С…РѕС‚СЏ Р±С‹ РїРёРЅРіСѓРµС‚СЃСЏ РїРѕ TCP:22.
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

