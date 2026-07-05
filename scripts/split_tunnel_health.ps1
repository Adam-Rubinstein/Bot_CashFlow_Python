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

function Invoke-SplitTunnelProbe(
    [string]$SshHost,
    [string]$RemoteProbeUrl,
    [string]$DeployPw,
    [string]$PlinkHostKey,
    [int]$TimeoutSeconds = 15
) {
    $remoteCmd = "curl -s -o /dev/null -w '%{http_code}' -X POST $RemoteProbeUrl -H 'Content-Type: application/json' -d '{}' 2>/dev/null"

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

function Test-SplitTunnelHealthy(
    [string]$SshHost,
    [string]$RemoteProbeUrl,
    [string]$DeployPw,
    [string]$PlinkHostKey,
    [int]$TimeoutSeconds = 15
) {
    $probe = Invoke-SplitTunnelProbe -SshHost $SshHost -RemoteProbeUrl $RemoteProbeUrl -DeployPw $DeployPw -PlinkHostKey $PlinkHostKey -TimeoutSeconds $TimeoutSeconds
    return $null -ne $probe -and $probe.Code -eq "403"
}
