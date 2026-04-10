# Проверка split-канала (ПК:8080 + VPS:18080) и при сбое — start_split_tunnel.ps1 -Force.
# Ставить в Планировщик: каждые 5 мин (см. docs/TROUBLESHOOTING_SPLIT.md).
$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
$Starter = Join-Path $Root "scripts\start_split_tunnel.ps1"
if (-not (Test-Path $Starter)) { $Root = "D:\Desktop\Projects\Bot_CashFlow_Python"; $Starter = Join-Path $Root "scripts\start_split_tunnel.ps1" }

$needRestart = $false

try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.ReceiveTimeout = 2000
    $tcp.SendTimeout = 2000
    $tcp.Connect("127.0.0.1", 8080)
    $tcp.Close()
} catch {
    $needRestart = $true
}

if (-not $needRestart) {
    # С VPS должен отвечать receiver (403 без подписи — норма)
    $raw = & ssh -o BatchMode=yes -o ConnectTimeout=10 root@62.60.186.183 "curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:18080/ -H 'Content-Type: application/json' -d '{}' 2>/dev/null"
    $code = if ($raw) { "$raw".Trim() } else { "" }
    if ($code -ne "403") {
        $needRestart = $true
    }
}

if ($needRestart) {
    & $Starter -Force
}
