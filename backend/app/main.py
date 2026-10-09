"""FastAPI application factory and lifespan wiring."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import settings
from app.core.enums import TOOL_NOTICE
from app.core.errors import MedBillError
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal, init_db
from app.providers import get_active_provider
from app.routes import benchmarks, bills, demo, health
from app.services.privacy_service import PrivacyService
from app.services.sample_documents import write_samples
from app.services.seeding import seed_benchmarks

logger = get_logger(__name__)

DESCRIPTION = """
**MedBill Lens** — hospital bill understanding and benchmark comparison.

Upload a hospital bill, correct the extracted charges, and compare each charge
against a benchmark dataset of comparable services.

### What this tool does not do

* It is **not** a diagnosis, legal, insurance-adjudication or fraud-detection tool.
* A charge that sits above a benchmark range is **not** an incorrect or unlawful
  charge. Benchmark data is limited and cannot account for every situation.
* Where no reliable benchmark exists, the tool says so instead of estimating.
* The bundled benchmark dataset is **synthetic demo data**, labelled as such
  everywhere it is used.

### AI usage

AI is used only for document understanding, categorization, explanations and
question generation. Every benchmark range, difference, percentage and status in
this API is computed deterministically in Python and is unaffected by the
configured AI provider. If the AI provider is unavailable, the API continues to
return complete numerical results with rule-based wording.
"""

TAGS_METADATA = [
    {"name": "bills", "description": "Upload, review and analyse a hospital bill."},
    {"name": "benchmarks", "description": "Browse the benchmark dataset and its sources."},
    {"name": "demo", "description": "Load synthetic sample bills (hackathon demo mode)."},
    {"name": "system", "description": "Health, disclaimers and enumeration metadata."},
]

_SWEEP_INTERVAL_SECONDS = 300


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("INFO" if settings.debug is False else "DEBUG")
    logger.info("starting app=%s env=%s", settings.app_name, settings.environment)

    init_db()
    if settings.seed_demo_benchmarks:
        with SessionLocal() as db:
            written = seed_benchmarks(db, config=settings)
        if written:
            logger.info("demo benchmark dataset ready")
    if settings.demo_mode:
        write_samples()

    provider = get_active_provider()
    status = await provider.health()
    logger.info("ai_provider name=%s ready=%s real=%s", status.name, status.ready, status.is_real)

    sweeper = asyncio.create_task(_sweep_loop())
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        await provider.aclose()
        logger.info("shutdown complete")


async def _sweep_loop() -> None:
    """Periodically delete expired raw documents and abandoned uploads."""
    while True:
        try:
            await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
            await asyncio.to_thread(_sweep_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the sweeper must never crash the app
            logger.warning("privacy_sweep_failed")


def _sweep_once() -> None:
    with SessionLocal() as db:
        privacy = PrivacyService(db, settings)
        purged = privacy.purge_expired()
        orphans = privacy.purge_orphans()
        if purged or orphans:
            logger.info("privacy_sweep purged=%s orphans=%s", purged, orphans)
        db.commit()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Remaining"],
    )

    # ------------------------------------------------------------------
    # Uniform, user-facing error handling. Never leak internals.
    # ------------------------------------------------------------------
    @app.exception_handler(MedBillError)
    async def _domain_error(_: Request, exc: MedBillError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        problems = [
            {
                "field": ".".join(str(p) for p in error.get("loc", []) if p not in ("body", "query")),
                "message": error.get("msg", "invalid value"),
            }
            for error in exc.errors()[:8]
        ]
        first = problems[0]["message"] if problems else "The request was not valid."
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Some of the details provided were not valid. Please check and try again.",
                    "detail": first,
                    "hint": "; ".join(f"{p['field']}: {p['message']}" for p in problems),
                }
            },
        )

    @app.exception_handler(ValidationError)
    async def _pydantic_error(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Some of the details provided were not valid.",
                    "detail": str(exc)[:400],
                    "hint": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side. Please try again.",
                    "detail": type(exc).__name__,
                    "hint": "If this keeps happening, please try again in a few moments.",
                }
            },
        )

    # ------------------------------------------------------------------
    app.include_router(health.router, prefix="/api")
    app.include_router(bills.router, prefix="/api")
    app.include_router(benchmarks.router, prefix="/api")
    app.include_router(demo.router, prefix="/api")

    @app.get("/api", tags=["system"])
    def index() -> dict:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/api/docs",
            "notice": TOOL_NOTICE,
            "endpoints": [
                "POST /api/bills/upload",
                "POST /api/bills/{id}/extract",
                "GET  /api/bills/{id}",
                "PUT  /api/bills/{id}/items",
                "POST /api/bills/preview",
                "POST /api/bills/{id}/analyze",
                "GET  /api/bills/{id}/analysis",
                "GET  /api/bills/{id}/report",
                "GET  /api/benchmarks",
                "GET  /api/benchmarks/stats",
                "GET  /api/health",
                "GET  /api/demo/scenarios",
            ],
        }

    return app


app = create_app()
