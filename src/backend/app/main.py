from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import ensure_token_on_startup
from .routes import router as config_router
from .sse import router as sse_router
from .ws import ws_router

app = FastAPI(title="Fix Assistant Backend", version="0.1.0")

# CORS allowlist: default to local dev origins; can be overridden via QC_CORS_ORIGINS
raw_origins = os.getenv(
    "QC_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:18000,http://127.0.0.1:18000",
)
allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    # Ensure token is available for protected endpoints
    ensure_token_on_startup()


@app.get("/health")
async def health():
    return {"status": "ok"}


# Routers
app.include_router(config_router)
app.include_router(sse_router)
app.include_router(ws_router)
