"""Demo mode endpoints.

Demo mode exists so the whole product can be demonstrated without an AI API
key. Every artefact it produces is labelled as demo data - it is never
presented as AI output or as real-world pricing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import DatasetLabel
from app.core.errors import MedBillError
from app.db.session import get_db
from app.providers import get_active_provider
from app.routes.deps import enforce_rate_limit
from app.schemas.analysis import AnalyzeResponse
from app.schemas.bill import UploadResponse
from app.services.analysis_service import AnalysisService
from app.services.bill_service import BillService
from app.services.sample_documents import write_samples
from app.services.seeding import create_scenario_bill, scenario_catalog

router = APIRouter(prefix="/demo", tags=["demo"])

_DEMO_DISABLED = "Demo mode is disabled on this server."
_UNKNOWN_SCENARIO = (
    "That demo scenario does not exist. Available scenarios are A, B and C."
)


def _require_demo(config: Settings) -> None:
    if not config.demo_mode:
        raise MedBillError(
            detail=_DEMO_DISABLED,
            code="demo_mode_disabled",
            user_message="Demo scenarios are not available on this server.",
            status_code=404,
        )


def _require_known_scenario(key: str) -> None:
    if key.upper() not in {"A", "B", "C"}:
        raise MedBillError(
            detail=f"Unknown scenario '{key}'.",
            code="scenario_not_found",
            user_message=_UNKNOWN_SCENARIO,
            status_code=404,
        )


@router.get("/scenarios")
def scenarios() -> dict:
    return {
        "scenarios": scenario_catalog(),
        "dataset_label": DatasetLabel.DEMO.value,
        "notice": (
            "Sample bills are synthetic. They contain fictional hospital names, "
            "fictional patient details and fictional amounts."
        ),
    }


@router.get("/sample-bills")
def sample_bills(config: Settings = Depends(get_settings)):
    """List (and generate on demand) the bundled sample documents."""
    paths = sorted(config.sample_bills_path.glob("*"))
    if not paths:
        paths = write_samples()
    return {
        "files": [
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "format": path.suffix.lstrip(".").lower(),
                "scenario": path.stem.rsplit("_", 1)[-1].upper() if "_" in path.stem else None,
            }
            for path in paths
            if path.is_file()
        ]
    }


@router.post(
    "/scenarios/{key}/load",
    response_model=UploadResponse,
    status_code=201,
    dependencies=[Depends(enforce_rate_limit)],
)
def load_scenario(
    key: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
):
    """Create a confirmed demo bill and return it ready for analysis."""
    _require_demo(config)
    _require_known_scenario(key)
    bill = create_scenario_bill(db, key, config=config)
    db.refresh(bill)
    service = BillService(db, config=config)
    return UploadResponse(
        bill=service.to_schema(bill),
        next_step="analyze",
        warnings=[
            "This is synthetic demo data. Hospital names, amounts and benchmark "
            "values are illustrative and must not be used for real-world decisions."
        ],
    )


@router.post(
    "/scenarios/{key}/run",
    response_model=AnalyzeResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
async def run_scenario(
    key: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
):
    """One-click demo: load a scenario and analyse it end to end."""
    _require_demo(config)
    _require_known_scenario(key)
    bill = create_scenario_bill(db, key, config=config)

    service = AnalysisService(db, config=config, provider=get_active_provider())
    analysis = await service.run(bill.id)
    questions = await service.bill_questions(bill.id)
    db.commit()
    db.refresh(analysis)
    return AnalyzeResponse(
        analysis=service.to_schema(analysis, questions=questions),
        messages=["Demo data - synthetic figures, not real-world prices."],
    )
