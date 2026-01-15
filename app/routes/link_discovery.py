from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import runtime
from app.ps import runner

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["link-discovery"])
_LAST_RESULT: Optional[Dict[str, Any]] = None
_NPCAP_CACHE: Dict[str, Any] = {"ts": 0.0, "installed": None}
_NPCAP_TTL = 5.0
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _cache_result(payload: Dict[str, Any]) -> None:
    global _LAST_RESULT
    _LAST_RESULT = {
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "npcap_installed": payload.get("npcap_installed"),
        "neighbors": payload.get("neighbors") or [],
        "protocols": payload.get("protocols"),
        "timestamp": time.time(),
    }


def get_link_status_summary() -> Dict[str, Any]:
    if _LAST_RESULT:
        neighbors = _LAST_RESULT.get("neighbors") or []
        summary = {
            "status": _LAST_RESULT.get("status") or "UNKNOWN",
            "reason": _LAST_RESULT.get("reason") or "No data",
            "npcap_installed": _LAST_RESULT.get("npcap_installed"),
        }
        if neighbors:
            summary["neighbors"] = len(neighbors)
        return summary
    installed = _npcap_installed()
    if installed:
        return {
            "status": "READY",
            "reason": "Npcap installed. Link discovery not run.",
            "npcap_installed": True,
        }
    return {
        "status": "UNAVAILABLE",
        "reason": "Npcap not installed",
        "npcap_installed": False,
    }


@router.get("/link-discovery")
def link_discovery() -> JSONResponse:
    installed = _npcap_installed()
    if not installed:
        payload = {
            "status": "UNAVAILABLE",
            "reason": "Npcap not installed",
            "npcap_installed": False,
            "tips": [
                "Install Npcap with WinPcap compatibility",
                "Ensure capture permissions are available",
                "Passive capture window will be 20 seconds",
            ],
            "download_url": "https://npcap.com/#download",
            "instructions": [
                "Download and install Npcap with WinPcap compatibility",
                "After install, restart fastLANe to enable Link Discovery",
            ],
            "restart_supported": True,
        }
        _cache_result(payload)
        return JSONResponse(status_code=200, content=payload)

    iface = _active_interface()
    capture = _capture_neighbors(iface, timeout=20)
    capture["npcap_installed"] = True
    _cache_result(capture)
    return JSONResponse(status_code=200, content=capture)


@router.get("/npcap-status")
def npcap_status() -> JSONResponse:
    installed = _npcap_installed()
    return JSONResponse(status_code=200, content={"npcap_installed": installed})


@router.post("/restart")
def restart_app() -> JSONResponse:
    runtime.request_restart()
    return JSONResponse(status_code=202, content={"status": "restarting"})


def _npcap_installed() -> bool:
    cached = _NPCAP_CACHE.get("installed")
    age = time.monotonic() - _NPCAP_CACHE.get("ts", 0.0)
    if cached is not None and age < _NPCAP_TTL:
        return bool(cached)

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidates = [
        os.path.join(system_root, "System32", "Npcap"),
        os.path.join(system_root, "System32", "Npcap", "wpcap.dll"),
        os.path.join(system_root, "System32", "wpcap.dll"),
        os.path.join(system_root, "System32", "drivers", "npcap.sys"),
        os.path.join(system_root, "SysWOW64", "Npcap"),
        os.path.join(system_root, "SysWOW64", "Npcap", "wpcap.dll"),
        os.path.join(system_root, "SysWOW64", "wpcap.dll"),
    ]
    if any(os.path.exists(path) for path in candidates):
        _NPCAP_CACHE["installed"] = True
        _NPCAP_CACHE["ts"] = time.monotonic()
        return True
    try:
        result = subprocess.run(
            ["sc", "query", "npcap"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        installed = result.returncode == 0
        _NPCAP_CACHE["installed"] = installed
        _NPCAP_CACHE["ts"] = time.monotonic()
        return installed
    except Exception:
        _NPCAP_CACHE["installed"] = False
        _NPCAP_CACHE["ts"] = time.monotonic()
        return False


def _active_interface() -> Optional[str]:
    info = runner.get_local_info()
    if info.get("ok"):
        return info.get("data", {}).get("active_interface")
    return None


def _capture_neighbors(iface: Optional[str], timeout: int = 20) -> Dict[str, Any]:
    try:
        from scapy.all import Ether, conf, sniff  # type: ignore
    except Exception as exc:
        return {
            "status": "UNAVAILABLE",
            "reason": f"Scapy not available: {exc}",
            "tips": ["Install scapy and restart fastLANe"],
            "restart_supported": True,
        }

    conf.use_pcap = True
    filter_expr = "ether proto 0x88cc or ether dst 01:00:0c:cc:cc:cc"

    try:
        packets = sniff(
            iface=iface,
            timeout=timeout,
            store=True,
            filter=filter_expr,
        )
    except Exception as exc:
        _LOG.warning("Link capture failed: %s", exc)
        return {
            "status": "UNAVAILABLE",
            "reason": f"Capture failed: {exc}",
            "tips": ["Run as admin or check Npcap install"],
            "restart_supported": True,
        }

    neighbors: List[Dict[str, Any]] = []
    seen = set()
    lldp_seen = False
    cdp_seen = False

    for pkt in packets:
        if not pkt.haslayer(Ether):
            continue
        eth = pkt[Ether]
        if eth.type == 0x88CC:
            lldp_seen = True
            payload = bytes(eth.payload)
            parsed = _parse_lldp(payload)
            if parsed:
                parsed["src_mac"] = eth.src
                parsed["protocol"] = "LLDP"
                key = (
                    parsed.get("chassis_id"),
                    parsed.get("port_id"),
                    parsed.get("system_name"),
                    eth.src,
                )
                if key not in seen:
                    seen.add(key)
                    neighbors.append(parsed)
        elif eth.dst.lower() == "01:00:0c:cc:cc:cc":
            cdp_seen = True

    status = "COMPLETE" if neighbors else "NO_NEIGHBORS"
    reason = "Neighbors discovered" if neighbors else "No LLDP neighbors detected"

    return {
        "status": status,
        "reason": reason,
        "interface": iface or "default",
        "duration_sec": timeout,
        "neighbors": neighbors,
        "protocols": {"lldp": lldp_seen, "cdp": cdp_seen},
        "tips": ["Ensure the switch is emitting LLDP/CDP frames"],
        "restart_supported": True,
    }


def _parse_lldp(payload: bytes) -> Dict[str, Any]:
    offset = 0
    data: Dict[str, Any] = {}
    while offset + 2 <= len(payload):
        header = (payload[offset] << 8) | payload[offset + 1]
        tlv_type = (header >> 9) & 0x7F
        tlv_len = header & 0x1FF
        offset += 2
        if tlv_type == 0:
            break
        if offset + tlv_len > len(payload):
            break
        value = payload[offset : offset + tlv_len]
        offset += tlv_len

        if tlv_type == 1:
            data["chassis_id"] = _parse_id_tlv(value)
        elif tlv_type == 2:
            data["port_id"] = _parse_id_tlv(value)
        elif tlv_type == 3 and tlv_len >= 2:
            data["ttl"] = int.from_bytes(value[:2], "big")
        elif tlv_type == 5:
            data["system_name"] = _decode_text(value)
        elif tlv_type == 6:
            data["system_desc"] = _decode_text(value)
        elif tlv_type == 8:
            mgmt = _parse_mgmt_address(value)
            if mgmt:
                data["management_address"] = mgmt
    return data


def _parse_id_tlv(value: bytes) -> str:
    if not value:
        return ""
    subtype = value[0]
    payload = value[1:]
    if subtype == 4 and payload:
        return _format_mac(payload)
    return _decode_text(payload)


def _parse_mgmt_address(value: bytes) -> Optional[str]:
    if len(value) < 2:
        return None
    addr_len = value[0]
    if addr_len < 2 or len(value) < 1 + addr_len:
        return None
    addr_subtype = value[1]
    addr_bytes = value[2 : 1 + addr_len]
    if addr_subtype == 1 and len(addr_bytes) == 4:
        return ".".join(str(b) for b in addr_bytes)
    return None


def _decode_text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="ignore").strip()


def _format_mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)
