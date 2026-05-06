# Проверка split-канала (ПК:8080 + VPS:18080) и при сбое — start_split_tunnel.ps1 -Force.
# Ставить в Планировщик: каждые 5 мин (см. docs/TROUBLESHOOTING_SPLIT.md).
$ErrorActionPreference = "SilentlyContinue"

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

$SshHost = if ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { "root@62.60.186.183" }
$RemoteProbeUrl = if ($env:CASHFLOW_REMOTE_PROBE_URL) { $env:CASHFLOW_REMOTE_PROBE_URL } else { "http://127.0.0.1:18080/" }
$PlinkHostKey = if ($env:CASHFLOW_PLINK_HOSTKEY) { $env:CASHFLOW_PLINK_HOSTKEY.Trim() } else { "SHA256:Bbpqi7aeMnjf4F+s4JpOlv/NoitFwXITg2ybMBJSpEY" }

$Root = if ($env:CASHFLOW_PROJECT_ROOT) { $env:CASHFLOW_PROJECT_ROOT } else { (Split-Path -Parent $PSScriptRoot) }
$Starter = Join-Path $Root "scripts\start_split_tunnel.ps1"
if (-not (Test-Path $Starter)) {
    $legacyRoot = "D:\Desktop\Projects\Bot_CashFlow_Python"
    $legacyStarter = Join-Path $legacyRoot "scripts\start_split_tunnel.ps1"
    if (Test-Path $legacyStarter) {
        $Root = $legacyRoot
        $Starter = $legacyStarter
    }
}

$deployPw = $null
if ($env:DEPLOY_SSH_PASSWORD -and $env:DEPLOY_SSH_PASSWORD.Trim().Length -gt 0) {
    $deployPw = $env:DEPLOY_SSH_PASSWORD.Trim()
} else {
    $fromFile = Read-DotEnvKey (Join-Path $Root ".env") "DEPLOY_SSH_PASSWORD"
    if ($fromFile -and $fromFile.Trim().Length -gt 0) { $deployPw = $fromFile.Trim() }
}

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
    # С VPS должен отвечать receiver (403 без подписи — норма).
    # Не вызывать ssh через & ssh: на Windows это поднимает консоль/conhost и «моргает» раз в N минут из планировщика.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $remoteCmd = "curl -s -o /dev/null -w '%{http_code}' -X POST $RemoteProbeUrl -H 'Content-Type: application/json' -d '{}' 2>/dev/null"
    if ($deployPw) {
        $plinkCmd = Get-Command plink.exe -ErrorAction SilentlyContinue
        if (-not $plinkCmd) {
            $needRestart = $true
        } else {
            $psi.FileName = $plinkCmd.Source
            $pwQ = $deployPw.Replace('"', '\"')
            $hkQ = $PlinkHostKey.Replace('"', '\"')
            $psi.Arguments = "-ssh -batch -hostkey `"$hkQ`" -pw `"$pwQ`" $SshHost `"$remoteCmd`""
        }
    } else {
        $psi.FileName = "ssh"
        $psi.Arguments = "-o BatchMode=yes -o ConnectTimeout=10 $SshHost `"$remoteCmd`""
    }
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    if (-not $needRestart) {
        try {
            [void]$p.Start()
            $raw = $p.StandardOutput.ReadToEnd()
            $null = $p.StandardError.ReadToEnd()
            $p.WaitForExit()
        } finally {
            if ($null -ne $p) { $p.Dispose() }
        }
        $code = if ($raw) { "$raw".Trim() } else { "" }
        if ($code -ne "403") {
            $needRestart = $true
        }
    }
}

if ($needRestart) {
    & $Starter -Force
}
