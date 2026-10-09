"""App factory: routers, middleware, error envelope and the outbox worker lifespan."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import models as _models  # noqa: F401  registers every table first
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import install_error_handlers
from app.core.logging import CorrelationIdMiddleware, configure_logging
from app.core.security import CsrfGuard
from app.events.worker import run_worker
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.counterparties.router import router as counterparties_router
from app.modules.demo.router import router as demo_router
from app.modules.fx.router import router as fx_router
from app.modules.invoices.router import router as invoices_router
from app.modules.members.router import router as members_router
from app.modules.network.router import router as network_router
from app.modules.notifications.router import router as notifications_router
from app.modules.pricing.router import router as pricing_router
from app.modules.runs.router import router as runs_router
from app.modules.settlement.router import router as settlement_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(stop)) if get_settings().worker_enabled else None
    try:
        yield
    finally:
        stop.set()
        if task:
            await task


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Wise Mesh Continental API",
        version="0.1.0",
        description="Multilateral invoice netting and settlement (hackathon prototype).",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    # Order: the correlation ID wraps everything, so even CSRF refusals carry one.
    app.add_middleware(CsrfGuard)
    app.add_middleware(CorrelationIdMiddleware)

    for router in (
        auth_router,
        members_router,
        fx_router,
        demo_router,
        invoices_router,
        counterparties_router,
        runs_router,
        settlement_router,
        pricing_router,
        network_router,
        notifications_router,
        admin_router,
    ):
        app.include_router(router)

    @app.get("/healthz", tags=["ops"], include_in_schema=False)
    def healthz() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return JSONResponse({"status": "ok", "database": "reachable"})
        except Exception:
            return JSONResponse({"status": "degraded", "database": "unreachable"}, 503)

    return app


app = create_app()
