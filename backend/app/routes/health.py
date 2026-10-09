"""Health and metadata endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import SAFE_DISCLAIMER, TOOL_NOTICE
from app.db.session import get_db
from app.providers import get_active_provider
from app.repositories.benchmark_repository import BenchmarkRepository
from app.schemas.bill import EnumOptionsResponse
from app.schemas.common import DisclaimerResponse, HealthResponse
from app.services.seeding import benchmark_metadata, scenario_catalog

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(db: Session = Depends(get_db), config: Settings = Depends(get_settings)):
    try:
        db.execute(text("SELECT 1"))
        database_state = "connected"
    except Exception:  # pragma: no cover - only on a broken database
        database_state = "unavailable"

    repo = BenchmarkRepository(db)
    try:
        records = repo.count()
    except Exception:  # pragma: no cover
        records = 0

    provider = get_active_provider()
    status = await provider.health()

    return HealthResponse(
        status="ok" if database_state == "connected" else "degraded",
        app=config.app_name,
        version=config.app_version,
        environment=config.environment,
        demo_mode=config.demo_mode,
        database=database_state,
        ai_provider=status.name,
        ai_provider_ready=status.ready,
        ai_provider_is_real=status.is_real,
        ai_fallback_enabled=config.ai_fallback_to_demo,
        benchmark_records=records,
        benchmark_label=benchmark_metadata(db)["dataset_label"],
        max_upload_size_mb=config.max_upload_size_mb,
        raw_file_retention_minutes=config.raw_file_retention_minutes,
        auth_enabled=config.auth_enabled,
        server_time=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/disclaimer", response_model=DisclaimerResponse)
def disclaimer(db: Session = Depends(get_db)) -> DisclaimerResponse:
    return DisclaimerResponse(
        main=SAFE_DISCLAIMER,
        tool_notice=TOOL_NOTICE,
        dataset_notice=benchmark_metadata(db)["dataset_label"],
        privacy_notice=(
            "Your uploaded bill may contain sensitive personal and financial "
            "information. Avoid uploading documents that you do not have permission "
            "to process. Files are processed in temporary storage and deleted "
            "automatically."
        ),
    )


@router.get("/options", response_model=EnumOptionsResponse)
def options(db: Session = Depends(get_db)) -> EnumOptionsResponse:
    """Enumerations and demo catalogue, so the UI never hard-codes vocabulary."""
    from app.core.enums import CATEGORY_LABELS, COUNTRY_LABELS, ChargeCategory, HospitalCategory, RoomCategory
    from app.models import BenchmarkPrice

    repo = BenchmarkRepository(db)
    cities = repo.distinct(BenchmarkPrice.city)
    countries = repo.distinct(BenchmarkPrice.country_code)
    treatments = [
        "General Surgery",
        "General Medicine",
        "Orthopaedics",
        "Cardiology",
        "Obstetrics & Gynaecology",
        "Paediatrics",
        "Orthopaedics and Joint Replacement",
    ]

    return EnumOptionsResponse(
        categories=[
            {"value": c.value, "label": CATEGORY_LABELS.get(c.value, c.value)}
            for c in ChargeCategory
        ],
        hospital_categories=[
            {"value": c.value, "label": c.value.replace("_", " ").title()}
            for c in HospitalCategory
        ],
        room_categories=[
            {"value": c.value, "label": c.value.replace("_", " ").title()}
            for c in RoomCategory
        ],
        cities=sorted(cities) or ["Kolkata", "Delhi", "Mumbai", "Bengaluru", "Chennai", "Hyderabad", "Pune", "Jaipur"],
        countries=[
            {"value": code, "label": COUNTRY_LABELS.get(code, code)}
            for code in sorted(countries) or ["IN"]
        ],
        treatments=treatments,
        demo_scenarios=scenario_catalog() if get_settings().demo_mode else [],
    )
