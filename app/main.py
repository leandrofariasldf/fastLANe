from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes import link_discovery, local_info, overview

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def _web_root() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "web"
    return Path(__file__).resolve().parent.parent / "web"


def create_app() -> FastAPI:
    app = FastAPI(title="fastLANe", version=overview.APP_VERSION)

    app.include_router(overview.router)
    app.include_router(local_info.router)
    app.include_router(link_discovery.router)

    web_dir = _web_root()
    if web_dir.exists():
        app.mount("/web", StaticFiles(directory=str(web_dir), html=True), name="web")

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/web/")

    return app


app = create_app()
