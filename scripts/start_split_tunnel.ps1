# Запуск receiver + обратный SSH-туннель на VPS (порт 18080 -> ПК:8080).
# По умолчанию: SSH-ключ без пароля. Иначе задайте DEPLOY_SSH_PASSWORD в .env или в окружении
# и установите PuTTY (plink.exe в PATH) — неинтерактивный пароль для штатного ssh.exe недоступен.
param(
    # -Force: full restart. Default (ensure): skip if receiver+ssh+tunnel OK (for watchdog).
    [switch]$Force,
    # Опционально: root@host или alias из ~/.ssh/config (например bot-prod-vps)
    [string]$SshHost = "",
    # Опционально: корень проекта Bot_CashFlow_Python
    [string]$ProjectRoot = "",
    # Опционально: формат ssh -R (remote:local), по умолчанию 127.0.0.1:18080:127.0.0.1:8080
    [string]$RemoteForward = ""
)
$ErrorActionPreference = "Stop"

function Read-DotEnvKey([string]$LiteralPath, [string]$Key) {
    if (-not (Test-Path -LiteralPath $LiteralPath)) { return $null }
    foreach ($line in Get-Content -LiteralPath $LiteralPath) {
        $t = $line.Trim()
        if ($t.Length -eq 0 -or $t.StartsWith("#")) { continue }
        $eq = $t.IndexOf("=")
        if ($eq -lt 1) { continue }
        $k = $t.Substring(0, $eq).Trim()
        if ($k -ne $Key) { continue }
        $v = $t.Substring($eq + 1).Trim()
        if ($v.Length -ge 2) {
            $a = $v[0]
            $b = $v[$v.Length - 1]
            if (($a -eq [char]34 -and $b -eq [char]34) -or ($a -eq [char]39 -and $b -eq [char]39)) {
                $v = $v.Substring(1, $v.Length - 2)
            }
        }
        return $v
    }
    return $null
}

$SshHost = if ($SshHost) { $SshHost } elseif ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { "root@62.60.186.183" }
$RemoteForward = if ($RemoteForward) { $RemoteForward } elseif ($env:CASHFLOW_REMOTE_FORWARD) { $env:CASHFLOW_REMOTE_FORWARD } else { "127.0.0.1:18080:127.0.0.1:8080" }
# plink -batch: host key must be trusted without registry cache (PuTTY «Cannot confirm a host key in batch mode»).
# Формат: SHA256: + 43 символа (документация PuTTY 4.19.3). Переопределение: $env:CASHFLOW_PLINK_HOSTKEY
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
        if ($found) { $Py = $found } else { throw "Нет venv и не найден Python: $Root\.venv\Scripts\python.exe" }
    }
    Write-Host "venv not found, using fallback Python: $Py"
}

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
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.ReceiveTimeout = 800
            $tcp.SendTimeout = 800
            $tcp.Connect("127.0.0.1", 8080)
            $tcp.Close()
            Write-Host "Receiver + SSH already running; port 8080 OK. Root: $Root"
            exit 0
        } catch {
            Write-Host "Processes exist but port 8080 not accepting - will restart. ($($_.Exception.Message))"
        }
    }
}

# Остановить старые экземпляры (тот же порт / тот же туннель)
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
  # У plink нет опции -keepalive (в отличие от OpenSSH); лишние токены приводили к мгновенному выходу процесса.
  $plinkArgs = @("-ssh", "-batch", "-hostkey", $PlinkHostKey, "-N", "-R", $RemoteForward, "-pw", $deployPw, $SshHost)
  Start-Process -FilePath $plinkExe -ArgumentList $plinkArgs -WindowStyle Hidden
  Write-Host "Receiver + plink reverse tunnel started. Root: $Root. Host: $SshHost. Forward: $RemoteForward"
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
