from __future__ import annotations

import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.ps import runner

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["local-info"])


@router.get("/local-info")
def local_info() -> JSONResponse:
    info = runner.get_local_info()
    if not info.get("ok"):
        _LOG.warning("Local info failed: %s", info.get("error"))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": info.get("error", "Failed to read local info"),
                    "detail": info.get("ps"),
                }
            },
        )
    return JSONResponse(status_code=200, content=info.get("data", {}))
