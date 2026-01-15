from __future__ import annotations

import threading

_restart_event = threading.Event()


def request_restart() -> None:
    _restart_event.set()


def restart_requested() -> bool:
    return _restart_event.is_set()


def wait_for_restart(timeout: float | None = None) -> bool:
    return _restart_event.wait(timeout)
