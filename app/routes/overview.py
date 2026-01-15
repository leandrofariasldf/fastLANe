from __future__ import annotations

import datetime as dt
import io
import json
import logging
import ipaddress
import platform
import socket
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.ps import runner
from app.routes import link_discovery

_LOG = logging.getLogger(__name__)

APP_VERSION = "0.1.0"
MAX_TEST_RESULTS = 10
LAST_TESTS: List[Dict[str, Any]] = []

router = APIRouter(prefix="/api", tags=["overview"])


def _store_test_result(entry: Dict[str, Any]) -> None:
    LAST_TESTS.append(entry)
    if len(LAST_TESTS) > MAX_TEST_RESULTS:
        del LAST_TESTS[0]


def _overview_status(local_info: Dict[str, Any]) -> Dict[str, Any]:
    status = "OK"
    findings: List[str] = []

    if not local_info:
        return {
            "status": "FAIL",
            "key_findings": ["No active interface detected"],
        }

    if not local_info.get("ip"):
        status = "FAIL"
        findings.append("No IPv4 address detected")

    if not local_info.get("gateway"):
        if status != "FAIL":
            status = "WARN"
        findings.append("Default gateway not detected")

    if local_info.get("dhcp_enabled") is False:
        if status == "OK":
            status = "WARN"
        findings.append("DHCP disabled")

    if not local_info.get("link_speed"):
        if status == "OK":
            status = "WARN"
        findings.append("Link speed unavailable")

    if not findings:
        findings.append("Interface is up with IPv4 configuration")

    return {"status": status, "key_findings": findings}


def _format_test_lines(test: Dict[str, Any]) -> List[str]:
    test_type = str(test.get("type", "unknown")).lower()
    lines = []
    lines.append(f"- Type: {test.get('type', 'unknown')}")
    lines.append(f"  Target: {test.get('target', 'unknown')}")
    lines.append(f"  Time: {test.get('timestamp', 'unknown')}")
    summary_text = _format_summary_text(test_type, test.get("summary"))
    if summary_text:
        lines.append(f"  Summary: {summary_text}")

    parsed = test.get("parsed")
    if not parsed:
        parsed = _safe_parse_json(test.get("stdout") or "")

    detail_lines = _format_detail_lines(test_type, parsed)
    if detail_lines:
        lines.append("  Details:")
        for line in detail_lines:
            lines.append(f"    {line}")
    else:
        stdout = test.get("stdout") or ""
        if stdout:
            lines.append("  Details:")
            for line in stdout.splitlines():
                lines.append(f"    {line}")

    stderr = test.get("stderr") or ""
    if stderr:
        lines.append("  Stderr:")
        for line in stderr.splitlines():
            lines.append(f"    {line}")
    return lines


def _safe_parse_json(text: str) -> Any:
    if not text:
        return None
    raw = text.strip()
    if not raw.startswith("{") and not raw.startswith("["):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _format_summary_text(test_type: str, summary: Any) -> str:
    if not summary:
        return ""
    if test_type == "ping":
        sent = summary.get("sent")
        received = summary.get("received")
        avg = summary.get("avg_ms")
        avg_text = f"{avg} ms" if avg is not None else "n/a"
        return f"Sent: {sent} | Received: {received} | Avg: {avg_text}"
    if test_type == "dns":
        return f"Records: {summary.get('record_count')}"
    if test_type == "tnc":
        remote_text = _format_remote_address(summary.get("remote_address"))
        return (
            f"Ping: {summary.get('ping_succeeded')} | "
            f"TCP: {summary.get('tcp_test_succeeded')} | "
            f"Remote: {remote_text}:{summary.get('remote_port')}"
        )
    if test_type == "tracert":
        return f"Hops: {summary.get('hop_count')}"
    return str(summary)


def _format_detail_lines(test_type: str, parsed: Any) -> List[str]:
    if not parsed:
        return []
    if test_type == "ping":
        items = parsed if isinstance(parsed, list) else [parsed]
        lines = []
        for idx, item in enumerate(items, start=1):
            address = item.get("Address")
            time_ms = item.get("ResponseTime")
            status = item.get("Status") or "OK"
            time_text = f"{time_ms} ms" if time_ms is not None else "n/a"
            lines.append(f"{idx}. {address} | {time_text} | {status}")
        return lines
    if test_type == "dns":
        items = parsed if isinstance(parsed, list) else [parsed]
        lines = []
        for item in items:
            if item.get("IPAddress"):
                lines.append(f"{item.get('Type') or 'A'} {item.get('Name')} -> {item.get('IPAddress')}")
            elif item.get("NameHost"):
                lines.append(f"{item.get('Type') or 'CNAME'} {item.get('Name')} -> {item.get('NameHost')}")
        return lines
    if test_type == "tnc":
        if isinstance(parsed, dict):
            remote_text = _format_remote_address(parsed.get("RemoteAddress"))
            return [
                f"Computer: {parsed.get('ComputerName')}",
                f"Remote: {remote_text}:{parsed.get('RemotePort')}",
                f"Ping: {parsed.get('PingSucceeded')}",
                f"TCP: {parsed.get('TcpTestSucceeded')}",
                f"Interface: {parsed.get('InterfaceAlias')}",
            ]
    if test_type == "tracert":
        if isinstance(parsed, dict):
            hops = parsed.get("hops") or []
            return [f"{hop.get('hop')}. {hop.get('raw')}" for hop in hops]
    return []


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


def _format_report_txt(
    timestamp: str,
    hostname: str,
    os_version: str,
    local_info: Dict[str, Any],
    link_status: Dict[str, Any],
    tests: List[Dict[str, Any]],
) -> str:
    dns_servers = local_info.get("dns_servers")
    if isinstance(dns_servers, str):
        dns_list = [dns_servers]
    else:
        dns_list = dns_servers or []
    lines = []
    lines.append("fastLANe Report")
    lines.append(f"Timestamp: {timestamp}")
    lines.append(f"Hostname: {hostname}")
    lines.append(f"OS: {os_version}")
    lines.append("")
    lines.append("Active Interface")
    if local_info:
        lines.append(f"  Interface: {local_info.get('active_interface')}")
        lines.append(f"  IP: {local_info.get('ip')}/{local_info.get('prefix')}")
        lines.append(f"  Gateway: {local_info.get('gateway')}")
        lines.append(f"  MAC: {local_info.get('mac')}")
        lines.append(f"  DNS: {', '.join(dns_list)}")
        lines.append(f"  DHCP: {local_info.get('dhcp_enabled')}")
        lines.append(f"  Link Speed: {local_info.get('link_speed')}")
        lines.append(f"  Gateway MAC: {local_info.get('gateway_mac')}")
        lines.append(f"  Gateway Vendor: {local_info.get('gateway_vendor')}")
    else:
        lines.append("  Unavailable")

    lines.append("")
    lines.append("Tests")
    if tests:
        for test in tests:
            lines.extend(_format_test_lines(test))
            lines.append("")
    else:
        lines.append("  No tests executed")

    lines.append("Link Discovery")
    lines.append(f"  Status: {link_status.get('status')}")
    lines.append(f"  Reason: {link_status.get('reason')}")

    return "\n".join(lines).strip() + "\n"


def _format_report_md(
    timestamp: str,
    hostname: str,
    os_version: str,
    local_info: Dict[str, Any],
    link_status: Dict[str, Any],
    tests: List[Dict[str, Any]],
) -> str:
    dns_servers = local_info.get("dns_servers")
    if isinstance(dns_servers, str):
        dns_list = [dns_servers]
    else:
        dns_list = dns_servers or []
    lines = []
    lines.append("# fastLANe Report")
    lines.append("")
    lines.append(f"- Timestamp: {timestamp}")
    lines.append(f"- Hostname: {hostname}")
    lines.append(f"- OS: {os_version}")
    lines.append("")
    lines.append("## Active Interface")
    if local_info:
        lines.append(f"- Interface: {local_info.get('active_interface')}")
        lines.append(f"- IP: {local_info.get('ip')}/{local_info.get('prefix')}")
        lines.append(f"- Gateway: {local_info.get('gateway')}")
        lines.append(f"- MAC: {local_info.get('mac')}")
        lines.append(f"- DNS: {', '.join(dns_list)}")
        lines.append(f"- DHCP: {local_info.get('dhcp_enabled')}")
        lines.append(f"- Link Speed: {local_info.get('link_speed')}")
        lines.append(f"- Gateway MAC: {local_info.get('gateway_mac')}")
        lines.append(f"- Gateway Vendor: {local_info.get('gateway_vendor')}")
    else:
        lines.append("- Unavailable")

    lines.append("")
    lines.append("## Tests")
    if tests:
        for test in tests:
            test_type = str(test.get("type", "unknown")).lower()
            lines.append(f"### {test.get('type', 'unknown').upper()} - {test.get('target', '')}")
            lines.append(f"- Time: {test.get('timestamp', 'unknown')}")
            summary_text = _format_summary_text(test_type, test.get("summary"))
            if summary_text:
                lines.append(f"- Summary: {summary_text}")

            parsed = test.get("parsed")
            if not parsed:
                parsed = _safe_parse_json(test.get("stdout") or "")
            detail_lines = _format_detail_lines(test_type, parsed)
            if detail_lines:
                lines.append("- Details:")
                for line in detail_lines:
                    lines.append(f"  - {line}")
            else:
                stdout = test.get("stdout") or ""
                if stdout:
                    lines.append("- Details:")
                    for line in stdout.splitlines():
                        lines.append(f"  - {line}")

            stderr = test.get("stderr") or ""
            if stderr:
                lines.append("- Errors:")
                for line in stderr.splitlines():
                    lines.append(f"  - {line}")
            lines.append("")
    else:
        lines.append("- No tests executed")

    lines.append("## Link Discovery")
    lines.append(f"- Status: {link_status.get('status')}")
    lines.append(f"- Reason: {link_status.get('reason')}")

    return "\n".join(lines).strip() + "\n"


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


@router.get("/overview")
def overview() -> JSONResponse:
    info = runner.get_local_info()
    local_data = info.get("data") if info.get("ok") else {}
    status_block = _overview_status(local_data)

    return JSONResponse(
        status_code=200,
        content={
            "status": status_block.get("status"),
            "key_findings": status_block.get("key_findings"),
            "active_interface": local_data.get("active_interface"),
            "ip": local_data.get("ip"),
            "gateway": local_data.get("gateway"),
            "link_speed": local_data.get("link_speed"),
        },
    )


@router.post("/run-test")
def run_test(payload: Dict[str, Any]) -> JSONResponse:
    test_type = (payload.get("type") or "").strip().lower()
    target = (payload.get("target") or "").strip()

    if not test_type or not target:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "type and target are required"}},
        )

    result = runner.run_test(test_type, target)
    timestamp = dt.datetime.now().isoformat(sep=" ", timespec="seconds")
    entry = {
        "type": test_type,
        "target": target,
        "timestamp": timestamp,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "summary": result.get("summary"),
        "parsed": result.get("parsed"),
    }
    _store_test_result(entry)

    if not result.get("ok"):
        _LOG.warning("Test failed: %s", result.get("stderr"))
        return JSONResponse(
            status_code=500,
            content={
                "error": {"message": result.get("stderr", "Test failed")},
                "stdout": result.get("stdout"),
                "stderr": result.get("stderr"),
                "parsed": result.get("parsed"),
                "summary": result.get("summary"),
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
            "parsed": result.get("parsed"),
            "summary": result.get("summary"),
        },
    )


@router.post("/export")
def export_report(payload: Dict[str, Any]) -> StreamingResponse:
    fmt = (payload.get("format") or "txt").lower()
    if fmt not in {"txt", "md"}:
        fmt = "txt"

    now = dt.datetime.now().isoformat(sep=" ", timespec="seconds")
    hostname = socket.gethostname()
    os_version = platform.platform()

    info = runner.get_local_info()
    local_data = info.get("data") if info.get("ok") else {}

    link_status = link_discovery.get_link_status_summary()
    if fmt == "md":
        content = _format_report_md(
            now,
            hostname,
            os_version,
            local_data,
            link_status,
            LAST_TESTS,
        )
        media_type = "text/markdown"
        ext = "md"
    else:
        content = _format_report_txt(
            now,
            hostname,
            os_version,
            local_data,
            link_status,
            LAST_TESTS,
        )
        media_type = "text/plain"
        ext = "txt"

    filename = f"fastlane_report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
    buffer = io.BytesIO(content.encode("utf-8"))

    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
