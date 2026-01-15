from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)
_LOCAL_INFO_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_LOCAL_INFO_TTL = 5.0
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parse_ps_json(text: str) -> Any:
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start_candidates = [raw.find("{"), raw.find("[")]
        start = min([idx for idx in start_candidates if idx != -1], default=-1)
        end = max(raw.rfind("}"), raw.rfind("]"))
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def run_ps(script: str, timeout: int = 20) -> Dict[str, Any]:
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "PowerShell timeout",
            "code": -1,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
            "code": -1,
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        _LOG.warning("PowerShell error (%s): %s", completed.returncode, stderr)

    return {
        "ok": completed.returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "code": completed.returncode,
    }


def run_cmd(cmd: List[str], timeout: int = 25) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "Command timeout",
            "code": -1,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
            "code": -1,
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    return {
        "ok": completed.returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "code": completed.returncode,
    }


def get_local_info() -> Dict[str, Any]:
    cached = _LOCAL_INFO_CACHE.get("data")
    if isinstance(cached, dict):
        age = time.monotonic() - _LOCAL_INFO_CACHE.get("ts", 0.0)
        if age < _LOCAL_INFO_TTL:
            return {"ok": True, "data": dict(cached), "cached": True}

    script = r'''
$cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1
if (-not $cfg) { $cfg = Get-NetIPConfiguration | Where-Object { $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1 }
if (-not $cfg) { return }
$ip = $cfg.IPv4Address | Select-Object -First 1
$dns = $cfg.DnsServer.ServerAddresses
$gw = $cfg.IPv4DefaultGateway.NextHop
$adapter = $cfg.NetAdapter
$dhcp = $cfg.NetIPv4Interface.Dhcp
[pscustomobject]@{
  active_interface = $adapter.Name
  ip = $ip.IPAddress
  prefix = $ip.PrefixLength
  gateway = $gw
  mac = $adapter.MacAddress
  dns_servers = $dns
  dhcp_enabled = ($dhcp -eq "Enabled")
  link_speed = $adapter.LinkSpeed
} | ConvertTo-Json -Depth 4 -Compress
'''

    result = run_ps(script, timeout=20)
    data = _parse_ps_json(result.get("stdout", ""))
    if not result.get("ok") or not data:
        return {
            "ok": False,
            "error": "Unable to read local network configuration",
            "ps": result,
        }

    gateway_ip = data.get("gateway") if isinstance(data, dict) else None
    gateway_mac = get_gateway_mac(gateway_ip) if gateway_ip else None
    data["gateway_mac"] = gateway_mac
    data["gateway_vendor"] = lookup_oui(gateway_mac)
    _LOCAL_INFO_CACHE["data"] = dict(data)
    _LOCAL_INFO_CACHE["ts"] = time.monotonic()

    return {"ok": True, "data": data}


def get_gateway_mac(gateway_ip: Optional[str]) -> Optional[str]:
    if not gateway_ip:
        return None

    result = run_cmd(["arp", "-a"], timeout=10)
    if not result.get("ok"):
        return None

    for line in result.get("stdout", "").splitlines():
        if gateway_ip in line:
            parts = line.split()
            if len(parts) >= 2:
                return parts[1]
    return None


def lookup_oui(mac: Optional[str]) -> str:
    if not mac:
        return "UNKNOWN"
    return "UNKNOWN"


def _format_remote_address(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        addr_val = value.get("Address")
        family = value.get("AddressFamily")
        if family == 2 and isinstance(addr_val, int):
            try:
                return str(ipaddress.IPv4Address(addr_val))
            except ipaddress.AddressValueError:
                return "unknown"
        return "unknown"
    return str(value)


def run_dns_test(target: str) -> Dict[str, Any]:
    script = (
        "Resolve-DnsName -Name "
        + _ps_quote(target)
        + " -ErrorAction Stop | Select-Object Name,Type,IPAddress,NameHost | ConvertTo-Json -Depth 4 -Compress"
    )
    result = run_ps(script, timeout=15)
    parsed = _parse_ps_json(result.get("stdout", ""))
    summary = None
    if parsed:
        if isinstance(parsed, dict):
            items = [parsed]
        else:
            items = parsed
        summary = {"record_count": len(items)}
    return {**result, "parsed": parsed, "summary": summary}


def run_ping_test(target: str) -> Dict[str, Any]:
    script = (
        "Test-Connection -ComputerName "
        + _ps_quote(target)
        + " -Count 4 -ErrorAction Stop | Select-Object Address,ResponseTime,Status | ConvertTo-Json -Depth 4 -Compress"
    )
    result = run_ps(script, timeout=20)
    parsed = _parse_ps_json(result.get("stdout", ""))
    summary = None
    if parsed:
        if isinstance(parsed, dict):
            items = [parsed]
        else:
            items = parsed
        successes = [item for item in items if item.get("Status") == "Success" or item.get("ResponseTime")]
        times = [item.get("ResponseTime") for item in successes if isinstance(item.get("ResponseTime"), (int, float))]
        avg_ms = round(sum(times) / len(times), 2) if times else None
        summary = {
            "sent": len(items),
            "received": len(successes),
            "avg_ms": avg_ms,
        }
    return {**result, "parsed": parsed, "summary": summary}


def run_tnc_test(target: str) -> Dict[str, Any]:
    script = (
        "Test-NetConnection -ComputerName "
        + _ps_quote(target)
        + " | Select-Object ComputerName,RemoteAddress,PingSucceeded,TcpTestSucceeded,RemotePort,InterfaceAlias | ConvertTo-Json -Depth 4 -Compress"
    )
    result = run_ps(script, timeout=20)
    parsed = _parse_ps_json(result.get("stdout", ""))
    summary = None
    if isinstance(parsed, dict):
        remote_text = _format_remote_address(parsed.get("RemoteAddress"))
        summary = {
            "ping_succeeded": parsed.get("PingSucceeded"),
            "tcp_test_succeeded": parsed.get("TcpTestSucceeded"),
            "remote_address": remote_text,
            "remote_port": parsed.get("RemotePort"),
        }
    return {**result, "parsed": parsed, "summary": summary}


def run_tracert(target: str) -> Dict[str, Any]:
    result = run_cmd(["tracert", "-d", "-h", "15", target], timeout=30)
    hops = []
    for line in result.get("stdout", "").splitlines():
        match = re.match(r"^\s*(\d+)\s+(.*)$", line)
        if match:
            hops.append({"hop": int(match.group(1)), "raw": match.group(2).strip()})
    parsed = {"hop_count": len(hops), "hops": hops} if hops else None
    summary = {"hop_count": len(hops)} if hops else None
    return {**result, "parsed": parsed, "summary": summary}


def run_test(test_type: str, target: str) -> Dict[str, Any]:
    test_type = test_type.lower()
    if test_type == "dns":
        return run_dns_test(target)
    if test_type == "ping":
        return run_ping_test(target)
    if test_type == "tnc":
        return run_tnc_test(target)
    if test_type == "tracert":
        return run_tracert(target)
    return {
        "ok": False,
        "stdout": "",
        "stderr": f"Unsupported test type: {test_type}",
        "code": -1,
        "parsed": None,
        "summary": None,
    }
