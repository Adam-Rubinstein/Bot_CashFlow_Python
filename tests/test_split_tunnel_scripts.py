from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_split_tunnel_health_helper_is_timeout_safe():
    text = _read("scripts/split_tunnel_health.ps1")
    assert "WaitForExit($TimeoutSeconds * 1000)" in text
    assert "CreateNoWindow = $true" in text
    assert "Invoke-SplitTunnelProbe" in text


def test_start_split_tunnel_uses_shared_health_probe_and_hostkey():
    text = _read("scripts/start_split_tunnel.ps1")
    assert "split_tunnel_health.ps1" in text
    assert "Test-SplitTunnelHealthy" in text
    plink_line = next(line for line in text.splitlines() if "$plinkArgs =" in line)
    assert "-hostkey" in plink_line
    assert "-keepalive" not in plink_line


def test_watch_split_tunnel_uses_shared_health_probe():
    text = _read("scripts/watch_split_tunnel.ps1")
    assert "split_tunnel_health.ps1" in text
    assert "Test-SplitTunnelHealthy" in text
    assert "start_split_tunnel.ps1 -Force" in text


def test_persistent_guardian_is_wired_to_hidden_launcher():
    guardian = _read("scripts/keep_split_tunnel_alive.ps1")
    launcher = _read("scripts/run_keep_split_tunnel_hidden.vbs")
    assert "Global\\BotCashFlowTunnelGuardian" in guardian
    assert "keep_split_tunnel_alive.ps1" in launcher
    assert "Test-SplitTunnelHealthy" in guardian
    assert "Start-Sleep -Seconds $CheckIntervalSeconds" in guardian
