#!/usr/bin/env python3
"""Single source of truth for VPS public IP (TaskManager deploy / SSH).

Canonical file: scripts/vps-public-ip.txt
(keep aligned with adam-mentor.ru/scripts/vps-public-ip.txt)

Priority:
  1. ADAM_VPS_PUBLIC_IP (emergency cutover override)
  2. scripts/vps-public-ip.txt
  3. sibling adam-mentor.ru/scripts/vps-public-ip.txt
  4. DEPLOY_SSH_HOST / ADAM_DEPLOY_HOST (host or user@host)

Do not hardcode the live IP in Python defaults or Cursor rules.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
PUBLIC_IP_FILE = _SCRIPTS / "vps-public-ip.txt"
_SIBLING_ADAM = _ROOT.parent / "adam-mentor.ru" / "scripts" / "vps-public-ip.txt"

_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _read_ip_file(path: Path) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if _IP_RE.match(line):
            return line
    return ""


def _env_ip(key: str) -> str:
    raw = (os.environ.get(key) or "").strip()
    if not raw:
        return ""
    if "@" in raw:
        raw = raw.partition("@")[2].strip()
    if _IP_RE.match(raw):
        return raw
    return ""


def public_ip(*, required: bool = True) -> str:
    for key in ("ADAM_VPS_PUBLIC_IP",):
        ip = _env_ip(key)
        if ip:
            return ip
    ip = _read_ip_file(PUBLIC_IP_FILE)
    if ip:
        return ip
    ip = _read_ip_file(_SIBLING_ADAM)
    if ip:
        return ip
    for key in ("DEPLOY_SSH_HOST", "ADAM_DEPLOY_HOST"):
        ip = _env_ip(key)
        if ip:
            return ip
    if required:
        raise RuntimeError(
            "VPS public IP unknown: set scripts/vps-public-ip.txt "
            "or ADAM_VPS_PUBLIC_IP "
            "(sibling adam-mentor.ru/scripts/vps-public-ip.txt also works)"
        )
    return ""


def deploy_ssh_host(*, user: str = "root") -> str:
    """user@ip for OpenSSH / paramiko. Always derived from public_ip()."""
    return f"{user}@{public_ip()}"


def dashed_ip(ip: str | None = None) -> str:
    return (ip or public_ip()).replace(".", "-")


def nip_host(ip: str | None = None, *, prefix: str = "adam-mentor") -> str:
    return f"{prefix}.{dashed_ip(ip)}.nip.io"


def tm_webhook_url(ip: str | None = None) -> str:
    return f"https://{nip_host(ip)}/taskmanager-bot/webhook"

