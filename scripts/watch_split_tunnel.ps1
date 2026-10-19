# РџСЂРѕРІРµСЂРєР° split-РєР°РЅР°Р»Р° (РџРљ:8080 + VPS:18080) Рё РїСЂРё СЃР±РѕРµ - start_split_tunnel.ps1 -Force.
# РЎС‚Р°РІРёС‚СЊ РІ РџР»Р°РЅРёСЂРѕРІС‰РёРє: РєР°Р¶РґС‹Рµ 5 РјРёРЅ (СЃРј. docs/TROUBLESHOOTING_SPLIT.md).
# Р•СЃР»Рё VPS:22 СЃ РџРљ РЅРµРґРѕСЃС‚СѓРїРµРЅ - РќР• РґРµР»Р°С‚СЊ -Force (Р°РЅС‚Рё-thrash / fail2ban).
$ErrorActionPreference = "SilentlyContinue"

. (Join-Path $PSScriptRoot "split_tunnel_health.ps1")

$SshHost = if ($env:CASHFLOW_VPS_SSH_HOST) { $env:CASHFLOW_VPS_SSH_HOST } else { (Get-VpsSshHost) }
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

$health = Get-SplitTunnelHealth -SshHost $SshHost -RemoteProbeUrl $RemoteProbeUrl -DeployPw $deployPw -PlinkHostKey $PlinkHostKey -TimeoutSeconds 15
Write-SplitTunnelLog $Root ("watch status={0} detail={1}" -f $health.Status, $health.Detail)

if ($health.Status -eq "Healthy") {
    exit 0
}
if ($health.Status -eq "VpsUnreachable") {
    # Р›РѕРєР°Р»СЊРЅС‹Р№ ensure Р±РµР· Force; РЅРµ РїР»РѕРґРёРј SSH Рє Р·Р°РєСЂС‹С‚РѕРјСѓ РїРѕСЂС‚Сѓ.
    & $Starter
    exit 0
}
& $Starter -Force

