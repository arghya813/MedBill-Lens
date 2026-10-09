"""Bill lifecycle: upload, extraction, review edits, totals, serialization."""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.enums import (
    ADDITIVE_CATEGORIES,
    CREDIT_CATEGORIES,
    NON_BENCHMARK_CATEGORIES,
    BillStatus,
    ChargeCategory,
)
from app.core.errors import BillNotConfirmedError, BillNotFoundError, NoChargesFoundError
from app.core.logging import get_logger
from app.models import Bill, BillItem, RawDocument
from app.providers import AIProvider, get_active_provider
from app.providers.base import DocumentInput, ExtractedBill
from app.repositories.bill_repository import AnalysisRepository, BillRepository
from app.schemas.bill import (
    BillContextInput,
    BillItemInput,
    BillItemOut,
    BillOut,
    BillTotalsOut,
    ExtractionMetaOut,
)
from app.services.categorization import categorize
from app.services.privacy_service import PrivacyService
from app.utils.money import round_money, sum_money
from app.utils.validation import ValidatedUpload

logger = get_logger(__name__)

#: Items below this confidence are highlighted for user confirmation.
LOW_CONFIDENCE_THRESHOLD = 0.7


class BillService:
    def __init__(
        self,
        db: Session,
        *,
        config: Settings | None = None,
        provider: AIProvider | None = None,
    ):
        self.db = db
        self.config = config or settings
        self.repo = BillRepository(db)
        self.analysis_repo = AnalysisRepository(db)
        self.privacy = PrivacyService(db, self.config)
        self.provider = provider or get_active_provider()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    def create_from_upload(
        self, upload: ValidatedUpload, content: bytes, *, source: str = "upload"
    ) -> tuple[Bill, RawDocument]:
        bill = self.repo.create(
            status=BillStatus.UPLOADED.value,
            source=source,
            currency_code=self.config.currency_code,
            extraction_meta={},
        )
        document = self.privacy.store(
            bill_id=bill.id,
            filename=upload.filename,
            content=content,
            content_type=upload.content_type,
            sha256=upload.sha256,
            detected_kind=upload.detected_kind,
        )
        bill.extraction_meta = {
            "original_filename": upload.filename,
            "sha256": upload.sha256,
            "size_bytes": upload.size_bytes,
            "detected_kind": upload.detected_kind,
        }
        self.db.flush()
        return bill, document

    def create_manual(
        self, *, items: list[BillItemInput], metadata=None, context=None
    ) -> Bill:
        bill = self.repo.create(
            status=BillStatus.AWAITING_CONFIRMATION.value,
            source="manual",
            currency_code=self.config.currency_code,
            extraction_meta={"method": "manual_entry"},
        )
        self._apply_metadata(bill, metadata)
        self._apply_context(bill, context)
        payloads = [self._item_payload(i, position) for position, i in enumerate(items)]
        for payload in payloads:
            payload["confidence"] = 1.0
            payload["is_user_verified"] = True
        self.repo.replace_items(bill, payloads)
        self.recompute_totals(bill)
        self.repo.confirm(bill)
        self.db.flush()
        return bill

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------
    async def extract(self, bill_id: str) -> Bill:
        bill = self._require(bill_id)
        documents = self.privacy.documents_for(bill_id)
        if not documents:
            raise BillNotFoundError("The uploaded document for this bill is no longer available.")

        document = documents[0]
        path = self.privacy._safe_path(document.stored_path)
        if path is None or not path.exists():
            raise BillNotFoundError(
                "The uploaded document has already been deleted by the retention policy. "
                "Please upload the bill again."
            )

        content = path.read_bytes()
        started = time.perf_counter()
        self.repo.set_status(bill, BillStatus.EXTRACTING.value)
        self.db.flush()

        from app.providers.document_text import extract_text_for

        kind = "pdf" if content.startswith(b"%PDF-") else "image"
        document_input = DocumentInput(
            filename=document.original_filename,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            # The raw bytes drive text extraction (pypdf / OCR).
            content_bytes=content,
            # Vision providers must only ever receive real raster images.
            # Passing PDF bytes here made the OpenAI-compatible provider attach
            # a "data:image/png" payload containing a PDF.
            image_bytes=content if kind == "image" else None,
            kind=kind,
        )
        text_result = extract_text_for(document_input)
        document_input.text = text_result.text
        self.privacy.store_text(document, text_result.text)

        extracted: ExtractedBill = await self.provider.extract_bill(document_input)
        duration_ms = int((time.perf_counter() - started) * 1000)

        warnings = [*text_result.warnings, *extracted.warnings]
        provider_name = getattr(extracted, "provider", "demo")
        provider_is_real = bool(getattr(self.provider, "last_used_real", False))

        if not extracted.items:
            self.repo.set_status(bill, BillStatus.FAILED.value)
            bill.extraction_meta = self._meta(
                document, text_result, extracted, duration_ms, provider_name, provider_is_real, warnings
            )
            self.db.flush()
            raise NoChargesFoundError(
                "We couldn't find any chargeable line items in this document. "
                "Please upload a clearer copy or enter the charges manually.",
                hint="Use the 'Enter charges manually' option on the upload page.",
            )

        self._apply_extracted(bill, extracted)

        payloads = []
        for position, item in enumerate(extracted.items):
            category = item.category if item.category in {c.value for c in ChargeCategory} else ChargeCategory.MISCELLANEOUS.value
            payloads.append(
                {
                    "description": item.description[:512],
                    "category": category,
                    "service_name": item.service_name,
                    "quantity": max(0.0, float(item.quantity or 0)),
                    "unit_price": max(0.0, float(item.unit_price or 0)),
                    "total_price": round_money(item.total_price),
                    "confidence": round(float(item.confidence or 0.5), 3),
                    "needs_confirmation": float(item.confidence or 0) < LOW_CONFIDENCE_THRESHOLD,
                    "source": "extraction",
                    "notes": item.notes,
                }
            )
        self.repo.replace_items(bill, payloads)
        self.recompute_totals(bill)
        self.repo.set_status(bill, BillStatus.AWAITING_CONFIRMATION.value)

        bill.extraction_meta = self._meta(
            document, text_result, extracted, duration_ms, provider_name, provider_is_real, warnings
        )
        self.db.flush()
        return bill

    def _meta(
        self, document, text_result, extracted, duration_ms, provider_name, provider_is_real, warnings
    ) -> dict:
        low_confidence = sum(
            1 for i in extracted.items if float(i.confidence or 0) < LOW_CONFIDENCE_THRESHOLD
        )
        return {
            "original_filename": document.original_filename,
            "provider": provider_name,
            "is_real_provider": provider_is_real,
            "method": extracted.method,
            "ocr_used": text_result.ocr_used,
            "text_length": text_result.length,
            "page_count": text_result.page_count,
            "low_confidence_items": low_confidence,
            "warnings": warnings,
            "duration_ms": duration_ms,
            "extraction_confidence": extracted.confidence,
        }

    def _apply_extracted(self, bill: Bill, extracted: ExtractedBill) -> None:
        bill.hospital_name = extracted.hospital_name
        bill.hospital_location = extracted.hospital_location
        bill.patient_name = extracted.patient_name
        bill.patient_id = extracted.patient_id
        bill.bill_number = extracted.bill_number
        bill.bill_date = extracted.bill_date
        bill.admission_date = extracted.admission_date
        bill.discharge_date = extracted.discharge_date
        if extracted.length_of_stay_days:
            bill.length_of_stay_days = extracted.length_of_stay_days
        elif bill.admission_date and bill.discharge_date:
            bill.length_of_stay_days = (bill.discharge_date - bill.admission_date).days
        bill.diagnosis = extracted.diagnosis
        bill.stated_grand_total = extracted.stated_grand_total
        if extracted.room_category:
            bill.room_category = extracted.room_category
        if extracted.city:
            bill.city = extracted.city

    # ------------------------------------------------------------------
    # Review / confirm
    # ------------------------------------------------------------------
    def update_items(
        self,
        bill_id: str,
        items: list[BillItemInput],
        *,
        metadata=None,
        context=None,
        mark_confirmed: bool = True,
    ) -> Bill:
        bill = self._require(bill_id)
        if not items:
            raise NoChargesFoundError("A bill must contain at least one charge.")

        payloads = [self._item_payload(item, position) for position, item in enumerate(items)]
        self.repo.replace_items(bill, payloads)
        self._apply_metadata(bill, metadata)
        self._apply_context(bill, context)
        self.recompute_totals(bill)

        if mark_confirmed:
            self.repo.confirm(bill)
            # Any previous analysis is stale once the numbers change.
            self.analysis_repo.clear_for_bill(bill_id)
        else:
            self.repo.set_status(bill, BillStatus.AWAITING_CONFIRMATION.value)
        self.db.flush()
        return self._require(bill_id)

    async def recategorize_item(self, bill_id: str, description: str, category_hint: str | None = None):
        rule_category, rule_confidence, reason = categorize(description, hint=category_hint)
        try:
            result = await self.provider.classify_charge(description, category_hint=category_hint)
        except Exception:  # pragma: no cover - provider already falls back internally
            return rule_category, rule_confidence, reason
        return result.category, result.confidence, result.reason or reason

    def _item_payload(self, item: BillItemInput, position: int) -> dict:
        total = item.total_price if item.total_price is not None else item.quantity * item.unit_price
        return {
            "description": item.description.strip(),
            "category": item.category,
            "service_name": item.service_name,
            "quantity": float(item.quantity or 0),
            "unit_price": round_money(item.unit_price or 0),
            "total_price": round_money(total or 0),
            "confidence": float(item.confidence if item.confidence is not None else 1.0),
            "is_user_verified": bool(item.is_user_verified),
            "user_edited": True,
            "needs_confirmation": False,
            "source": item.source or "user",
            "notes": item.notes,
        }

    def _apply_metadata(self, bill: Bill, metadata) -> None:
        if metadata is None:
            return
        for field in (
            "hospital_name",
            "hospital_location",
            "patient_name",
            "patient_id",
            "bill_number",
            "bill_date",
            "admission_date",
            "discharge_date",
            "diagnosis",
        ):
            value = getattr(metadata, field, None)
            if value is not None:
                setattr(bill, field, value)
        room = getattr(metadata, "room_category", None)
        if room:
            bill.room_category = room
        if bill.admission_date and bill.discharge_date:
            bill.length_of_stay_days = (bill.discharge_date - bill.admission_date).days
        self.db.flush()

    def _apply_context(self, bill: Bill, context: BillContextInput | None) -> None:
        if context is None:
            return
        if context.city is not None:
            bill.city = context.city
        if context.country is not None:
            bill.country = context.country
        if context.hospital_category is not None:
            bill.hospital_category = context.hospital_category
        if context.treatment is not None:
            bill.treatment = context.treatment
        if context.room_category is not None:
            bill.room_category = context.room_category
        self.db.flush()

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------
    def recompute_totals(self, bill: Bill) -> Bill:
        additive = sum_money(
            i.total_price for i in bill.items if i.category in ADDITIVE_CATEGORIES
        )
        taxes = sum_money(i.total_price for i in bill.items if i.category == ChargeCategory.TAX.value)
        credits = sum_money(i.total_price for i in bill.items if i.category in CREDIT_CATEGORIES)
        discounts = sum_money(
            i.total_price for i in bill.items if i.category == ChargeCategory.DISCOUNT.value
        )
        insurance = sum_money(
            i.total_price for i in bill.items if i.category == ChargeCategory.INSURANCE.value
        )
        other = sum_money(
            i.total_price
            for i in bill.items
            if i.category in NON_BENCHMARK_CATEGORIES
            and i.category != ChargeCategory.TAX.value
            and i.category not in CREDIT_CATEGORIES
        )

        computed = round_money(additive + taxes + other + credits)
        if bill.stated_grand_total:
            # Trust the printed total when the items reconcile closely with it.
            item_sum = round_money(
                sum_money(i.total_price for i in bill.items)
            )
            if abs(item_sum - bill.stated_grand_total) <= max(1.0, bill.stated_grand_total * 0.005):
                bill.grand_total = round_money(bill.stated_grand_total)
            else:
                bill.grand_total = computed
        else:
            bill.grand_total = computed

        bill.subtotal = additive
        bill.taxes_total = taxes
        bill.discounts_total = discounts
        bill.insurance_deduction = insurance
        self.db.flush()
        return bill

    def compute_totals_output(self, bill: Bill) -> BillTotalsOut:
        items_total = round_money(sum_money(i.total_price for i in bill.items))
        grand = round_money(bill.grand_total if bill.grand_total is not None else items_total)
        stated = bill.stated_grand_total
        mismatch_amount = 0.0
        mismatch = False
        if stated and abs(items_total - stated) > 1:
            mismatch = True
            mismatch_amount = round_money(items_total - stated)
        return BillTotalsOut(
            items_total=items_total,
            subtotal=round_money(bill.subtotal or 0),
            taxes_total=round_money(bill.taxes_total or 0),
            discounts_total=round_money(bill.discounts_total or 0),
            insurance_deduction=round_money(bill.insurance_deduction or 0),
            grand_total=grand,
            stated_grand_total=stated,
            total_mismatch=mismatch,
            mismatch_amount=mismatch_amount,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_schema(self, bill: Bill) -> BillOut:
        meta = bill.extraction_meta or {}
        totals = self.compute_totals_output(bill)
        return BillOut(
            id=bill.id,
            status=bill.status,
            source=bill.source,
            is_demo=bill.is_demo,
            hospital_name=bill.hospital_name,
            hospital_location=bill.hospital_location,
            city=bill.city,
            country=bill.country,
            hospital_category=bill.hospital_category,
            treatment=bill.treatment,
            room_category=bill.room_category,
            patient_name=bill.patient_name,
            patient_id=bill.patient_id,
            bill_number=bill.bill_number,
            bill_date=bill.bill_date,
            admission_date=bill.admission_date,
            discharge_date=bill.discharge_date,
            length_of_stay_days=bill.length_of_stay_days,
            diagnosis=bill.diagnosis,
            subtotal=bill.subtotal,
            taxes_total=bill.taxes_total,
            discounts_total=bill.discounts_total,
            insurance_deduction=bill.insurance_deduction,
            grand_total=bill.grand_total,
            stated_grand_total=bill.stated_grand_total,
            currency_code=bill.currency_code or "INR",
            confirmed_at=bill.confirmed_at,
            created_at=bill.created_at,
            updated_at=bill.updated_at,
            items=[
                BillItemOut(
                    id=item.id,
                    position=item.position,
                    description=item.description,
                    category=item.category,
                    service_name=item.service_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                    confidence=item.confidence,
                    is_user_verified=item.is_user_verified,
                    user_edited=item.user_edited,
                    needs_confirmation=item.needs_confirmation,
                    source=item.source,
                    notes=item.notes,
                )
                for item in sorted(bill.items, key=lambda i: i.position)
            ],
            totals=totals,
            extraction=ExtractionMetaOut(
                provider=meta.get("provider", "demo"),
                is_real_provider=bool(meta.get("is_real_provider")),
                method=meta.get("method", "unknown"),
                ocr_used=bool(meta.get("ocr_used")),
                text_length=int(meta.get("text_length", 0) or 0),
                low_confidence_items=int(meta.get("low_confidence_items", 0) or 0),
                warnings=list(meta.get("warnings", [])),
                duration_ms=int(meta.get("duration_ms", 0) or 0),
            ),
            has_analysis=self.analysis_repo.get_for_bill(bill.id) is not None,
        )

    # ------------------------------------------------------------------
    def _require(self, bill_id: str) -> Bill:
        bill = self.repo.get(bill_id)
        if bill is None:
            raise BillNotFoundError(f"No bill exists with id '{bill_id}'.")
        return bill

    def require_confirmed(self, bill_id: str) -> Bill:
        bill = self._require(bill_id)
        if bill.status not in {
            BillStatus.CONFIRMED.value,
            BillStatus.ANALYZING.value,
            BillStatus.COMPLETED.value,
        }:
            raise BillNotConfirmedError()
        return bill
