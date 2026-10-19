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

function Get-SshTargetHost([string]$SshHost) {
    if ([string]::IsNullOrWhiteSpace($SshHost)) { return $SshHost }
    $at = $SshHost.LastIndexOf("@")
    if ($at -ge 0 -and $at -lt ($SshHost.Length - 1)) {
        return $SshHost.Substring($at + 1).Trim()
    }
    return $SshHost.Trim()
}

function Get-SshTargetUser([string]$SshHost) {
    if ([string]::IsNullOrWhiteSpace($SshHost)) { return "root" }
    $at = $SshHost.LastIndexOf("@")
    if ($at -gt 0) { return $SshHost.Substring(0, $at).Trim() }
    return "root"
}

function Test-TcpPortOpen(
    [string]$HostName,
    [int]$Port = 22,
    [int]$TimeoutMs = 3000
) {
    if ([string]::IsNullOrWhiteSpace($HostName)) { return $false }
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs)) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        if ($client) { try { $client.Close() } catch {} }
    }
}

function Ensure-PlinkSshKeepalive(
    [string]$SessionName = "BotCashFlowReverse",
    [string]$HostName,
    [string]$UserName = "root",
    [int]$PingIntervalSec = 30
) {
    # У plink нет CLI -keepalive; SSH keepalive задаётся в сохранённой сессии PuTTY (PingInterval).
    if ([string]::IsNullOrWhiteSpace($HostName)) { return $null }
    $regKey = ($SessionName -replace " ", "%20")
    $path = "HKCU:\Software\SimonTatham\PuTTY\Sessions\$regKey"
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -Path $path -Force | Out-Null
    }
    New-ItemProperty -LiteralPath $path -Name "HostName" -Value $HostName -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $path -Name "UserName" -Value $UserName -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $path -Name "Protocol" -Value "ssh" -PropertyType String -Force | Out-Null
    New-ItemProperty -LiteralPath $path -Name "PortNumber" -Value 22 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -LiteralPath $path -Name "PingInterval" -Value $PingIntervalSec -PropertyType DWord -Force | Out-Null
    return $SessionName
}

function Invoke-SplitTunnelProbe(
    [string]$SshHost,
    [string]$RemoteProbeUrl,
    [string]$DeployPw,
    [string]$PlinkHostKey,
    [int]$TimeoutSeconds = 15
) {
    $remoteCmd = "curl -s -o /dev/null -w '%{http_code}' -m 5 -X POST $RemoteProbeUrl -H 'Content-Type: application/json' -d '{}' 2>/dev/null"

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    if ($DeployPw) {
        $plinkCmd = Get-Command plink.exe -ErrorAction SilentlyContinue
        if (-not $plinkCmd) { return $null }
        $psi.FileName = if ($plinkCmd.Source) { $plinkCmd.Source } elseif ($plinkCmd.Path) { $plinkCmd.Path } else { "plink.exe" }
        $pwQ = $DeployPw.Replace('"', '\"')
        $hkQ = $PlinkHostKey.Replace('"', '\"')
        $psi.Arguments = "-ssh -batch -hostkey `"$hkQ`" -pw `"$pwQ`" $SshHost `"$remoteCmd`""
    } else {
        $sshCmd = Get-Command ssh -ErrorAction SilentlyContinue
        if (-not $sshCmd) { return $null }
        $psi.FileName = if ($sshCmd.Source) { $sshCmd.Source } elseif ($sshCmd.Path) { $sshCmd.Path } else { "ssh" }
        $psi.Arguments = "-o BatchMode=yes -o ConnectTimeout=10 $SshHost `"$remoteCmd`""
    }

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    try {
        [void]$p.Start()
        if (-not $p.WaitForExit($TimeoutSeconds * 1000)) {
            try { $p.Kill() } catch {}
            return $null
        }
        $stdout = $p.StandardOutput.ReadToEnd().Trim()
        $stderr = $p.StandardError.ReadToEnd().Trim()
        return [pscustomobject]@{
            Code = $stdout
            ExitCode = $p.ExitCode
            StdErr = $stderr
        }
    } catch {
        return $null
    } finally {
        if ($p) { $p.Dispose() }
    }
}

function Get-SplitTunnelHealth(
    [string]$SshHost,
    [string]$RemoteProbeUrl,
    [string]$DeployPw,
    [string]$PlinkHostKey,
    [int]$TimeoutSeconds = 15,
    [int]$TcpTimeoutMs = 3000
) {
    $hostName = Get-SshTargetHost $SshHost
    if (-not (Test-TcpPortOpen -HostName $hostName -Port 22 -TimeoutMs $TcpTimeoutMs)) {
        return [pscustomobject]@{
            Status = "VpsUnreachable"
            Code = $null
            Detail = "TCP ${hostName}:22 not open from PC"
        }
    }
    $probe = Invoke-SplitTunnelProbe -SshHost $SshHost -RemoteProbeUrl $RemoteProbeUrl -DeployPw $DeployPw -PlinkHostKey $PlinkHostKey -TimeoutSeconds $TimeoutSeconds
    if ($null -ne $probe -and $probe.Code -eq "403") {
        return [pscustomobject]@{
            Status = "Healthy"
            Code = "403"
            Detail = "VPS probe 403 OK"
        }
    }
    $code = if ($null -eq $probe) { $null } else { $probe.Code }
    $err = if ($null -eq $probe) { "probe timeout/null" } else { $probe.StdErr }
    return [pscustomobject]@{
        Status = "TunnelBroken"
        Code = $code
        Detail = "VPS:22 up but tunnel probe failed (code=$code; $err)"
    }
}

function Test-SplitTunnelHealthy(
    [string]$SshHost,
    [string]$RemoteProbeUrl,
    [string]$DeployPw,
    [string]$PlinkHostKey,
    [int]$TimeoutSeconds = 15
) {
    $health = Get-SplitTunnelHealth -SshHost $SshHost -RemoteProbeUrl $RemoteProbeUrl -DeployPw $DeployPw -PlinkHostKey $PlinkHostKey -TimeoutSeconds $TimeoutSeconds
    return $health.Status -eq "Healthy"
}

function Write-SplitTunnelLog([string]$Root, [string]$Message) {
    try {
        $dir = Join-Path $Root "logs"
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message
        Add-Content -LiteralPath (Join-Path $dir "split_tunnel_guardian.log") -Value $line -Encoding UTF8
    } catch {}
}
