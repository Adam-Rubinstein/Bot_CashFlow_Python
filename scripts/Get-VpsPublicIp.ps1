# Single source: scripts/vps-public-ip.txt (sync with adam-mentor.ru).
function Get-VpsPublicIp {
  $candidates = @(
    (Join-Path $PSScriptRoot 'vps-public-ip.txt'),
    'D:\Desktop\Projects\adam-mentor.ru\scripts\vps-public-ip.txt',
    'D:\Desktop\Projects\TaskManager\scripts\vps-public-ip.txt'
  )
  foreach ($p in $candidates) {
    if (-not (Test-Path -LiteralPath $p)) { continue }
    foreach ($raw in Get-Content -LiteralPath $p -ErrorAction SilentlyContinue) {
      $line = "$raw".Trim()
      if (-not $line -or $line.StartsWith('#')) { continue }
      if ($line -match '^\d{1,3}(\.\d{1,3}){3}$') { return $line }
    }
  }
  throw 'VPS public IP unknown: set scripts/vps-public-ip.txt'
}

function Get-VpsSshHost {
  param([string]$User = 'root')
  return ("{0}@{1}" -f $User, (Get-VpsPublicIp))
}
