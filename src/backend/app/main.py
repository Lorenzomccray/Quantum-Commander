from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Optional instrumentation (enabled via env; imports are best-effort)
try:
    from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
except Exception:  # pragma: no cover - optional
    Instrumentator = None  # type: ignore

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore
except Exception:  # pragma: no cover - optional
    FastAPIInstrumentor = None  # type: ignore

from .auth import ensure_token_on_startup
from .routes import router as config_router
from .sse import router as sse_router
from .ws import ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Ensure token is available for protected endpoints
    ensure_token_on_startup()
    # Shared HTTP client for outbound calls
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
    try:
        yield
    finally:
        try:
            await app.state.http.aclose()  # type: ignore[attr-defined]
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="Fix Assistant Backend", version="0.1.0", lifespan=lifespan)

    # Optional metrics and tracing (activate only if libs available and env enabled)
    if os.getenv("QC_METRICS", "0") not in {"0", "false", "False", ""} and (
        Instrumentator is not None
    ):
        try:
            Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        except Exception:
            pass

    if os.getenv("QC_OTEL", "0") not in {"0", "false", "False", ""} and (
        FastAPIInstrumentor is not None
    ):
        try:
            FastAPIInstrumentor.instrument_app(app)
        except Exception:
            pass

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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Optional legacy UI mount (guarded by QC_EXPOSE_WEB_UI and existence of ui/dist)
    # Mount under "/ui" so API routes (e.g., "/assistant/*") are never shadowed by static serving.
    EXPOSE_WEB_UI = str(os.getenv("QC_EXPOSE_WEB_UI", "0")).lower() not in {"0", "false", ""}
    UI_DIR = Path(__file__).resolve().parents[3] / "ui" / "dist"
    if EXPOSE_WEB_UI and UI_DIR.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

    # Routers
    app.include_router(config_router)
    app.include_router(sse_router)
    app.include_router(ws_router)

    return app


app = create_app()
