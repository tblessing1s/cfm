"""Entrypoint for the CFM analytics FastAPI service."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .app.routers.trades_router import router as trades_router
import importlib
import logging

app = FastAPI(title="CFM Juice Analytics API")


@app.on_event("startup")
async def prewarm_heavy_modules():
    """Pre-import heavy third-party modules to avoid startup latency on first request."""
    logger = logging.getLogger("cfm.main")
    modules = ["openpyxl", "requests", "urllib3"]
    for mod in modules:
        try:
            importlib.import_module(mod)
            logger.info(f"Pre-warmed module: {mod}")
        except Exception as exc:
            logger.warning(f"Failed to pre-warm module {mod}: {exc}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://localhost:4600",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades_router, prefix="/api")
