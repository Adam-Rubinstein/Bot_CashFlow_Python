# Запуск receiver + обратный SSH-туннель на VPS (порт 18080 -> ПК:8080).
# Требуется: ключ SSH к root@62.60.186.183 без пароля.
param(
    # Принудительно перезапустить (убить процессы и поднять заново). По умолчанию: если receiver и ssh уже есть — выход без рестарта (для watchdog).
    [switch]$Force
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$Root\receiver.py")) { $Root = "D:\Desktop\Projects\Bot_CashFlow_Python" }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Нет venv: $Py" }

if (-not $Force) {
    $receiverOk = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine -match "receiver\.py" -and $_.CommandLine -match [regex]::Escape($Root)
    })
    $sshOk = @(Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and $_.CommandLine -match "18080:127\.0\.0\.1:8080"
    })
    if ($receiverOk.Count -ge 1 -and $sshOk.Count -ge 1) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.ReceiveTimeout = 800
            $tcp.SendTimeout = 800
            $tcp.Connect("127.0.0.1", 8080)
            $tcp.Close()
            Write-Host "Receiver + SSH already running; port 8080 OK. Root: $Root"
            exit 0
        } catch {
            Write-Host "Processes exist but port 8080 not accepting — will restart. ($($_.Exception.Message))"
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
Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
  $cmd = $_.CommandLine
  if ($cmd -match "18080:127\.0\.0\.1:8080") {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

Start-Sleep -Milliseconds 500

Start-Process -FilePath $Py -ArgumentList "receiver.py" -WorkingDirectory $Root -WindowStyle Hidden
Start-Sleep -Seconds 3

$sshArgs = @(
  "-N",
  "-o", "ServerAliveInterval=30",
  "-o", "ServerAliveCountMax=3",
  "-o", "ExitOnForwardFailure=yes",
  "-R", "127.0.0.1:18080:127.0.0.1:8080",
  "root@62.60.186.183"
)
# Hidden — без отдельного окна ssh (не закрыть случайно; процесс в фоне)
Start-Process -FilePath "ssh" -ArgumentList $sshArgs -WindowStyle Hidden

Write-Host "Receiver + SSH reverse tunnel started (no ssh window). Root: $Root"
