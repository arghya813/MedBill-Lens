"""Bill endpoints: upload, extract, review, analyze, report, questions."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import (
    CorruptDocumentError,
    ExtractionFailedError,
    FileTooLargeError,
    InvalidFileTypeError,
    MedBillError,
)
from app.core.logging import get_logger
from app.db.session import get_db
from app.models import Bill
from app.providers import get_active_provider
from app.repositories.bill_repository import AnalysisRepository, BillRepository
from app.routes.deps import enforce_rate_limit, require_auth_if_enabled
from app.schemas.analysis import (
    AnalyzeResponse,
    PreviewRequest,
    PreviewResponse,
    ReportRequest,
    ReportResponse,
)
from app.schemas.bill import (
    BillContextInput,
    BillMetadataInput,
    BillItemInput,
    ExtractResponse,
    ManualBillCreateRequest,
    UpdateBillItemsRequest,
    UploadResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.bill_service import BillService
from app.services.privacy_service import PrivacyService
from app.services.report_service import ReportService
from app.utils.validation import validate_upload

logger = get_logger(__name__)

router = APIRouter(prefix="/bills", tags=["bills"])

#: Reported to the client so the progress UI can advance realistically.
EXTRACTION_STAGES = [
    "Uploading bill...",
    "Reading document...",
    "Extracting charges...",
    "Categorizing services...",
    "Preparing analysis...",
]

_CHUNK = 1024 * 256


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_rate_limit), Depends(require_auth_if_enabled)],
)
async def upload_bill(
    file: Annotated[UploadFile, File(description="Hospital bill PDF, JPG or PNG")],
    db: Session = Depends(get_db),
    config: Settings = Depends(get_settings),
) -> UploadResponse:
    """Store an uploaded document and create a bill in ``uploaded`` state.

    The file is written to private temporary storage only. It is never served
    over HTTP and is deleted automatically after
    ``RAW_FILE_RETENTION_MINUTES``.
    """
    content = await _read_limited(file, config)
    validated = validate_upload(file.filename or "bill", content, file.content_type, config)

    service = BillService(db, config=config)
    bill, _document = service.create_from_upload(validated, content)
    db.commit()
    db.refresh(bill)

    logger.info("bill_uploaded bill=%s bytes=%s", bill.id, validated.size_bytes)
    return UploadResponse(
        bill=service.to_schema(bill),
        next_step="extract",
        warnings=[
            "Your document is stored temporarily and is deleted automatically. It is "
            "never exposed through a public URL."
        ],
    )


async def _read_limited(file: UploadFile, config: Settings) -> bytes:
    limit = config.max_upload_bytes
    buffer = bytearray()
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise FileTooLargeError(
                f"File exceeds the {config.max_upload_size_mb} MB limit."
            )
    return bytes(buffer)


@router.post(
    "/{bill_id}/extract",
    response_model=ExtractResponse,
    dependencies=[Depends(enforce_rate_limit), Depends(require_auth_if_enabled)],
)
async def extract_bill(
    bill_id: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
) -> ExtractResponse:
    """Run document understanding and return the structured bill for review."""
    service = BillService(db, config=config, provider=get_active_provider())
    try:
        bill = await service.extract(bill_id)
    except MedBillError as exc:
        # Keep the bill row so the user can retry or switch to manual entry.
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 - converted to a user-facing error
        logger.exception("extraction_unexpected_error bill=%s", bill_id)
        db.commit()
        raise ExtractionFailedError(f"{type(exc).__name__}: {exc}") from exc

    db.commit()
    db.refresh(bill)
    warnings = list((bill.extraction_meta or {}).get("warnings", []))
    return ExtractResponse(bill=service.to_schema(bill), warnings=warnings, requires_confirmation=True)


@router.get("/{bill_id}", dependencies=[Depends(enforce_rate_limit)])
def get_bill(
    bill_id: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
):
    service = BillService(db, config=config)
    bill = service.repo.get(bill_id)
    if bill is None:
        from app.core.errors import BillNotFoundError

        raise BillNotFoundError(f"No bill exists with id '{bill_id}'.")
    return service.to_schema(bill)


@router.put("/{bill_id}/items", dependencies=[Depends(enforce_rate_limit)])
def update_bill_items(
    bill_id: str,
    payload: UpdateBillItemsRequest,
    db: Session = Depends(get_db),
    config: Settings = Depends(get_settings),
):
    """Persist user corrections and confirm the bill.

    Benchmark analysis only runs after this succeeds.
    """
    service = BillService(db, config=config)
    bill = service.update_items(
        bill_id,
        payload.items,
        metadata=payload.metadata,
        context=payload.context,
        mark_confirmed=payload.mark_confirmed,
    )
    db.commit()
    db.refresh(bill)
    return service.to_schema(bill)


@router.post(
    "/preview",
    response_model=PreviewResponse,
    dependencies=[Depends(enforce_rate_limit), Depends(require_auth_if_enabled)],
)
def preview_bill(
    payload: PreviewRequest,
    db: Session = Depends(get_db),
    config: Settings = Depends(get_settings),
) -> PreviewResponse:
    """Compare the charges on the review screen without confirming them.

    Deliberately available before confirmation: the review screen is where the
    user corrects what extraction read, and these flags are what they correct
    against. It writes nothing and consults no AI provider, so it is safe to
    call as often as the form changes.
    """
    return AnalysisService(db, config=config).preview(payload)


@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_rate_limit), Depends(require_auth_if_enabled)],
)
def create_manual_bill(
    payload: ManualBillCreateRequest,
    db: Session = Depends(get_db),
    config: Settings = Depends(get_settings),
):
    """Enter charges by hand when a document cannot be read."""
    service = BillService(db, config=config)
    bill = service.create_manual(
        items=payload.items, metadata=payload.metadata, context=payload.context
    )
    db.commit()
    db.refresh(bill)
    return UploadResponse(
        bill=service.to_schema(bill), next_step="analyze", warnings=["Entered manually."]
    )


@router.post(
    "/{bill_id}/analyze",
    response_model=AnalyzeResponse,
    dependencies=[Depends(enforce_rate_limit), Depends(require_auth_if_enabled)],
)
async def analyze_bill(
    bill_id: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
) -> AnalyzeResponse:
    """Compare the confirmed bill against benchmarks.

    All numbers are produced by the deterministic engine. The AI provider only
    contributes the written explanations, questions and summary.
    """
    service = AnalysisService(db, config=config, provider=get_active_provider())
    analysis = await service.run(bill_id)
    questions = await service.bill_questions(bill_id)
    db.commit()
    db.refresh(analysis)
    return AnalyzeResponse(
        analysis=service.to_schema(analysis, questions=questions),
        messages=[],
    )


@router.get(
    "/{bill_id}/analysis",
    dependencies=[Depends(enforce_rate_limit)],
)
def get_analysis(
    bill_id: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
):
    service = AnalysisService(db, config=config)
    analysis = AnalysisRepository(db).get_for_bill(bill_id)
    if analysis is None:
        from app.core.errors import AnalysisNotReadyError

        raise AnalysisNotReadyError(
            "No analysis is available for this bill yet. Confirm the bill data and run "
            "the analysis first."
        )
    questions = analysis.meta.get("questions", []) if analysis.meta else []
    return service.to_schema(analysis, questions=questions)


@router.get(
    "/{bill_id}/report",
    dependencies=[Depends(enforce_rate_limit)],
)
def get_report(
    bill_id: str,
    format: str = Query(default="json", pattern="^(json|html|markdown)$"),
    hide_patient_name: bool = Query(default=True),
    hide_patient_id: bool = Query(default=True),
    hide_bill_number: bool = Query(default=True),
    hide_hospital_name: bool = Query(default=False),
    include_questions: bool = Query(default=True),
    include_sources: bool = Query(default=True),
    db: Session = Depends(get_db),
    config: Settings = Depends(get_settings),
):
    """Build a shareable report. Patient identifiers are hidden by default."""
    service = ReportService(db, config=config)
    return service.build(
        bill_id,
        ReportRequest(
            hide_patient_name=hide_patient_name,
            hide_patient_id=hide_patient_id,
            hide_bill_number=hide_bill_number,
            hide_hospital_name=hide_hospital_name,
            include_questions=include_questions,
            include_sources=include_sources,
            format=format,
        ),
    )


@router.post(
    "/{bill_id}/questions",
    dependencies=[Depends(enforce_rate_limit), Depends(require_auth_if_enabled)],
)
async def regenerate_questions(
    bill_id: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
):
    service = AnalysisService(db, config=config, provider=get_active_provider())
    questions = await service.bill_questions(bill_id)
    analysis = AnalysisRepository(db).get_for_bill(bill_id)
    if analysis is not None:
        meta = dict(analysis.meta or {})
        meta["questions"] = questions
        analysis.meta = meta
        db.commit()
    return {"bill_id": bill_id, "questions": questions}


@router.delete("/{bill_id}", dependencies=[Depends(enforce_rate_limit)])
def delete_bill(
    bill_id: str, db: Session = Depends(get_db), config: Settings = Depends(get_settings)
):
    """Delete a bill and any raw documents immediately."""
    repo = BillRepository(db)
    bill = repo.get(bill_id)
    if bill is None:
        from app.core.errors import BillNotFoundError

        raise BillNotFoundError(f"No bill exists with id '{bill_id}'.")
    PrivacyService(db, config).purge_bill(bill_id)
    repo.delete(bill)
    db.commit()
    return {"deleted": True, "bill_id": bill_id}
