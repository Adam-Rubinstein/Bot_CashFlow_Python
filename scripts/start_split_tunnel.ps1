# Р—Р°РїСѓСЃРє receiver + РѕР±СЂР°С‚РЅС‹Р№ SSH-С‚СѓРЅРЅРµР»СЊ РЅР° VPS (РїРѕСЂС‚ 18080 -> РџРљ:8080).
# РџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ: SSH-РєР»СЋС‡ Р±РµР· РїР°СЂРѕР»СЏ. РРЅР°С‡Рµ Р·Р°РґР°Р№С‚Рµ DEPLOY_SSH_PASSWORD РІ .env РёР»Рё РІ РѕРєСЂСѓР¶РµРЅРёРё
# Рё СѓСЃС‚Р°РЅРѕРІРёС‚Рµ PuTTY (plink.exe РІ PATH) - РЅРµРёРЅС‚РµСЂР°РєС‚РёРІРЅС‹Р№ РїР°СЂРѕР»СЊ РґР»СЏ С€С‚Р°С‚РЅРѕРіРѕ ssh.exe РЅРµРґРѕСЃС‚СѓРїРµРЅ.
param(
    # -Force: full restart. Default (ensure): skip if receiver+ssh+tunnel OK (for watchdog).
    [switch]$Force,
    # РћРїС†РёРѕРЅР°Р»СЊРЅРѕ: root@host РёР»Рё alias РёР· ~/.ssh/config (РЅР°РїСЂРёРјРµСЂ bot-prod-vps)
    [string]$SshHost = "",
    # РћРїС†РёРѕРЅР°Р»СЊРЅРѕ: РєРѕСЂРµРЅСЊ РїСЂРѕРµРєС‚Р° Bot_CashFlow_Python
    [string]$ProjectRoot = "",
    # РћРїС†РёРѕРЅР°Р»СЊРЅРѕ: С„РѕСЂРјР°С‚ ssh -R (remote:local), РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ 127.0.0.1:18080:127.0.0.1:8080
    [string]$RemoteForward = ""
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'Get-VpsPublicIp.ps1')

. (Join-Path $PSScriptRoot "split_tunnel_health.ps1")

$SshHost = if ($SshHost) { $SshHost } elseif ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { (Get-VpsSshHost) }
$RemoteForward = if ($RemoteForward) { $RemoteForward } elseif ($env:CASHFLOW_REMOTE_FORWARD) { $env:CASHFLOW_REMOTE_FORWARD } else { "127.0.0.1:18080:127.0.0.1:8080" }
# plink -batch: host key must be trusted without registry cache (PuTTY В«Cannot confirm a host key in batch modeВ»).
# Р¤РѕСЂРјР°С‚: SHA256: + 43 СЃРёРјРІРѕР»Р° (РґРѕРєСѓРјРµРЅС‚Р°С†РёСЏ PuTTY 4.19.3). РџРµСЂРµРѕРїСЂРµРґРµР»РµРЅРёРµ: $env:CASHFLOW_PLINK_HOSTKEY
$PlinkHostKey = if ($env:CASHFLOW_PLINK_HOSTKEY) { $env:CASHFLOW_PLINK_HOSTKEY.Trim() } else { "SHA256:Bbpqi7aeMnjf4F+s4JpOlv/NoitFwXITg2ybMBJSpEY" }

$Root = if ($ProjectRoot) { $ProjectRoot } elseif ($env:CASHFLOW_PROJECT_ROOT) { $env:CASHFLOW_PROJECT_ROOT } else { (Split-Path -Parent $PSScriptRoot) }
if (-not (Test-Path "$Root\receiver.py")) {
    $legacyRoot = "D:\Desktop\Projects\Bot_CashFlow_Python"
    if (Test-Path "$legacyRoot\receiver.py") {
        $Root = $legacyRoot
    } else {
        throw "receiver.py not found. Set -ProjectRoot or CASHFLOW_PROJECT_ROOT."
    }
}

$deployPw = $null
if ($env:DEPLOY_SSH_PASSWORD -and $env:DEPLOY_SSH_PASSWORD.Trim().Length -gt 0) {
    $deployPw = $env:DEPLOY_SSH_PASSWORD.Trim()
} else {
    $fromFile = Read-DotEnvKey (Join-Path $Root ".env") "DEPLOY_SSH_PASSWORD"
    if ($fromFile -and $fromFile.Trim().Length -gt 0) { $deployPw = $fromFile.Trim() }
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    # Fallback: py launcher or system Python (see TaskManager start_local_bot_services.ps1)
    $pyLauncher = "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Launcher\py.exe"
    if (Test-Path $pyLauncher) {
        $Py = $pyLauncher
    } else {
        $candidates = @(
            "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python313\python.exe",
            "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\python.exe",
            "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python311\python.exe",
            "C:\Python313\python.exe", "C:\Python312\python.exe",
            "C:\Program Files\Python313\python.exe"
        )
        $found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($found) { $Py = $found } else { throw "РќРµС‚ venv Рё РЅРµ РЅР°Р№РґРµРЅ Python: $Root\.venv\Scripts\python.exe" }
    }
    Write-Host "venv not found, using fallback Python: $Py"
}

$vpsHost = Get-SshTargetHost $SshHost
$vpsUser = Get-SshTargetUser $SshHost
$vpsTcpOpen = Test-TcpPortOpen -HostName $vpsHost -Port 22 -TimeoutMs 3000

if (-not $Force) {
    $receiverOk = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine -match "receiver\.py" -and $_.CommandLine -match [regex]::Escape($Root)
    })
    $rfEsc = [regex]::Escape($RemoteForward)
    $tunnelOk = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return $false }
        $n = $_.Name
        if ($n -eq "ssh.exe" -and $cmd -match $rfEsc) { return $true }
        if ($n -eq "plink.exe" -and $cmd -match $rfEsc) { return $true }
        return $false
    })
    if ($receiverOk.Count -ge 1 -and $tunnelOk.Count -ge 1) {
        if (-not $vpsTcpOpen) {
            Write-Host "Receiver + tunnel processes exist; VPS ${vpsHost}:22 unreachable from PC - skip restart (anti-thrash). Root: $Root"
            exit 0
        }
        if (Test-SplitTunnelHealthy -SshHost $SshHost -RemoteProbeUrl "http://127.0.0.1:18080/" -DeployPw $deployPw -PlinkHostKey $PlinkHostKey -TimeoutSeconds 15) {
            Write-Host "Receiver + SSH already running; VPS probe 403 OK. Root: $Root"
            exit 0
        } else {
            Write-Host "Processes exist but VPS probe is unhealthy - will restart."
        }
    } elseif (-not $vpsTcpOpen -and $receiverOk.Count -ge 1 -and $tunnelOk.Count -eq 0) {
        # Р•СЃС‚СЊ receiver, РЅРµС‚ С‚СѓРЅРЅРµР»СЏ, VPS Р·Р°РєСЂС‹С‚ - РЅРµ СЃС‚Р°СЂС‚СѓРµРј plink РєР°Р¶РґС‹Рµ N СЃРµРєСѓРЅРґ.
        Write-Host "VPS ${vpsHost}:22 unreachable; receiver up, tunnel absent - skip plink start (anti-thrash). Root: $Root"
        exit 0
    }
}

# РћСЃС‚Р°РЅРѕРІРёС‚СЊ СЃС‚Р°СЂС‹Рµ СЌРєР·РµРјРїР»СЏСЂС‹ (С‚РѕС‚ Р¶Рµ РїРѕСЂС‚ / С‚РѕС‚ Р¶Рµ С‚СѓРЅРЅРµР»СЊ)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
  $cmd = $_.CommandLine
  if ($cmd -and $cmd -match "receiver\.py" -and $cmd -match [regex]::Escape($Root)) {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
}
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -in @("ssh.exe", "plink.exe") -and $_.CommandLine -and $_.CommandLine -match [regex]::Escape($RemoteForward)
} | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 500

Start-Process -FilePath $Py -ArgumentList "receiver.py" -WorkingDirectory $Root -WindowStyle Hidden
Start-Sleep -Seconds 3

if ($deployPw) {
  $plinkCmd = Get-Command plink.exe -ErrorAction SilentlyContinue
  if (-not $plinkCmd) {
    throw "DEPLOY_SSH_PASSWORD is set but plink.exe not found in PATH. Install PuTTY or use an SSH key and remove DEPLOY_SSH_PASSWORD."
  }
  $plinkExe = $plinkCmd.Source
  # plink has no CLI -keepalive (fake flag killed process). Keepalive via PuTTY session PingInterval.
  $sessionName = Ensure-PlinkSshKeepalive -SessionName "BotCashFlowReverse" -HostName $vpsHost -UserName $vpsUser -PingIntervalSec 30
  $plinkArgs = @(
    "-load", $sessionName,
    "-ssh", "-batch", "-hostkey", $PlinkHostKey,
    "-N", "-R", $RemoteForward,
    "-pw", $deployPw,
    $SshHost
  )
  Start-Process -FilePath $plinkExe -ArgumentList $plinkArgs -WindowStyle Hidden
  Write-Host "Receiver + plink reverse tunnel started (session=$sessionName PingInterval=30). Root: $Root. Host: $SshHost. Forward: $RemoteForward"
} else {
  $sshArgs = @(
    "-N",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "-R", $RemoteForward,
    $SshHost
  )
  Start-Process -FilePath "ssh" -ArgumentList $sshArgs -WindowStyle Hidden
  Write-Host "Receiver + SSH reverse tunnel started (no ssh window). Root: $Root. Host: $SshHost. Forward: $RemoteForward"
}

