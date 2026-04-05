# Запуск receiver + обратный SSH-туннель на VPS (порт 18080 -> ПК:8080).
# Требуется: ключ SSH к root@62.60.186.183 без пароля.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$Root\receiver.py")) { $Root = "D:\Desktop\Projects\Bot_CashFlow_Python" }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Нет venv: $Py" }

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
Start-Sleep -Seconds 2

$sshArgs = @(
  "-N",
  "-o", "ServerAliveInterval=30",
  "-o", "ServerAliveCountMax=3",
  "-o", "ExitOnForwardFailure=yes",
  "-R", "127.0.0.1:18080:127.0.0.1:8080",
  "root@62.60.186.183"
)
Start-Process -FilePath "ssh" -ArgumentList $sshArgs -WindowStyle Minimized

Write-Host "Receiver + SSH reverse tunnel started. Root: $Root"
