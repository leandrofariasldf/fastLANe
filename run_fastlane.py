from __future__ import annotations

import argparse
import logging
import os
import json
import datetime as dt
import threading
import time
import sys
import subprocess
from urllib.request import Request, urlopen

import uvicorn
import webbrowser

try:
    import webview
except Exception:
    webview = None

from app import runtime
from app.main import app as fastlane_app

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
_LOG = logging.getLogger(__name__)
logging.raiseExceptions = False
_PYWEBVIEW_LOG = logging.getLogger("pywebview")
_PYWEBVIEW_LOG.disabled = True
_PYWEBVIEW_LOG.propagate = False
_PYWEBVIEW_LOG.handlers.clear()


class ExportApi:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.window = None

    def set_window(self, window: "webview.Window") -> None:
        self.window = window

    def save_report(self, fmt: str) -> dict:
        if fmt not in {"txt", "md"}:
            fmt = "txt"
        if not self.window:
            return {"ok": False, "error": "Window not ready"}

        try:
            timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fastlane_report_{timestamp}.{fmt}"
            path = self.window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=filename,
            )
            if isinstance(path, (list, tuple)):
                path = path[0] if path else None
            if not path:
                return {"ok": False, "cancelled": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        def _worker(target_path: str) -> None:
            try:
                data = json.dumps({"format": fmt}).encode("utf-8")
                req = Request(
                    f"{self.base_url}/api/export",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=20) as response:
                    content = response.read()
                    disposition = response.headers.get("Content-Disposition", "")
                filename = f"fastlane_report.{fmt}"
                if "filename=" in disposition:
                    filename = disposition.split("filename=")[-1].strip().strip('"')
                if target_path.lower().endswith((".txt", ".md")) is False:
                    target_path = f"{target_path}.{fmt}"
                with open(target_path, "wb") as handle:
                    handle.write(content)
                payload = {"ok": True, "path": target_path, "filename": filename}
            except Exception as exc:
                payload = {"ok": False, "error": str(exc)}
            try:
                self.window.evaluate_js(f"window.fastlaneExportDone({json.dumps(payload)});")
            except Exception:
                pass

        threading.Thread(target=_worker, args=(path,), daemon=True).start()
        return {"ok": True, "pending": True, "path": path}

    def open_export(self, path: str) -> dict:
        try:
            os.startfile(path)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_export_folder(self, path: str) -> dict:
        try:
            subprocess.run(["explorer", f"/select,{path}"], check=False)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


def _wait_for_server(url: str, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fastLANe diagnostics UI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9876, help="Bind port (default: 9876)")
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run API only (no embedded UI window)",
    )
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/web/"
    health_url = f"http://{args.host}:{args.port}/api/health"

    config = uvicorn.Config(fastlane_app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if args.no_ui:
        thread.join()
        return

    if webview is None:
        _LOG.error("pywebview is not installed. Install requirements or run with --no-ui.")
        thread.join()
        return

    _wait_for_server(health_url)

    api = ExportApi(f"http://{args.host}:{args.port}")
    window = webview.create_window(
        "fastLANe",
        url,
        width=1280,
        height=800,
        min_size=(920, 640),
        js_api=api,
    )
    api.set_window(window)

    def _shutdown() -> None:
        server.should_exit = True

    window.events.closed += _shutdown

    def _restart_watch() -> None:
        if runtime.wait_for_restart():
            try:
                window.destroy()
            except Exception:
                pass

    restart_thread = threading.Thread(target=_restart_watch, daemon=True)
    restart_thread.start()
    try:
        webview.start(gui="edgechromium", debug=False, private_mode=True)
    except Exception as exc:
        _LOG.error("pywebview failed to start: %s", exc)
        _LOG.info("Opening browser fallback: %s", url)
        try:
            webbrowser.open(url)
        except Exception:
            _LOG.error("Browser fallback failed.")
        thread.join()
        return
    server.should_exit = True
    thread.join(timeout=2)

    if runtime.restart_requested():
        _LOG.info("Restarting fastLANe...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    main()
