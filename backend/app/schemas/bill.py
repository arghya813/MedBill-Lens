"""Pydantic schemas for the bill domain."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    ADDITIVE_CATEGORIES,
    CREDIT_CATEGORIES,
    ChargeCategory,
    HospitalCategory,
    RoomCategory,
)
from app.schemas.common import ORMModel

VALID_CATEGORIES = {c.value for c in ChargeCategory}
MAX_ITEMS = 400
MAX_DESCRIPTION_LENGTH = 512

#: Request bodies reject unknown keys instead of ignoring them. ``metadata``
#: and ``context`` are separate objects with an overlapping ``room_category``,
#: so a client that puts a context field in the wrong place used to get a 200
#: with silently different - and wrong - benchmark matching. A 422 is safer.
_STRICT = ConfigDict(extra="forbid")


class BillItemInput(BaseModel):
    """A line item as supplied by the user (review screen) or by extraction."""

    id: str | None = Field(default=None, description="Existing item id when editing")
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    category: str = Field(default=ChargeCategory.MISCELLANEOUS.value)
    service_name: str | None = Field(default=None, max_length=255)
    quantity: float = Field(default=1.0, ge=0, le=100000)
    # Credit lines (discounts, insurance) are legitimately negative, so the
    # floor is negative rather than zero: rejecting them made any bill with a
    # discount impossible to save from the review screen.
    unit_price: float = Field(default=0.0, ge=-100_000_000, le=100_000_000)
    total_price: float | None = Field(default=None, ge=-100_000_000, le=100_000_000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_user_verified: bool = False
    user_edited: bool = False
    source: str = Field(default="user", max_length=32)
    notes: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value):
        if value is None:
            return ChargeCategory.MISCELLANEOUS.value
        return str(value).strip().lower().replace(" ", "_").replace("-", "_")

    @field_validator("quantity", mode="before")
    @classmethod
    def _coerce_quantity(cls, value):
        if value in (None, ""):
            return 1.0
        return value

    @field_validator("unit_price", mode="before")
    @classmethod
    def _coerce_unit_price(cls, value):
        if value in (None, ""):
            return 0.0
        return value

    @model_validator(mode="after")
    def _fill_total(self):
        if self.total_price is None:
            object.__setattr__(self, "total_price", round(self.quantity * self.unit_price, 2))
        return self

    @property
    def is_credit(self) -> bool:
        return self.category in CREDIT_CATEGORIES

    @property
    def is_additive(self) -> bool:
        return self.category in ADDITIVE_CATEGORIES

    @property
    def effective_amount(self) -> float:
        return -abs(self.total_price) if self.is_credit else self.total_price


class BillContextInput(BaseModel):
    """Comparison context supplied by the user, used to select benchmarks."""

    model_config = _STRICT

    city: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=8)
    hospital_category: str | None = Field(default=None, max_length=32)
    treatment: str | None = Field(default=None, max_length=255)
    room_category: str | None = Field(default=None, max_length=32)

    @field_validator("hospital_category", "room_category", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        if value is None:
            return None
        text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        return text or None

    @field_validator("city", "treatment", mode="before")
    @classmethod
    def _trim(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("country", mode="before")
    @classmethod
    def _country_code(cls, value):
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None


class BillMetadataInput(BaseModel):
    model_config = _STRICT

    hospital_name: str | None = Field(default=None, max_length=255)
    hospital_location: str | None = Field(default=None, max_length=255)
    patient_name: str | None = Field(default=None, max_length=255)
    patient_id: str | None = Field(default=None, max_length=120)
    bill_number: str | None = Field(default=None, max_length=120)
    bill_date: date | None = None
    admission_date: date | None = None
    discharge_date: date | None = None
    room_category: str | None = Field(default=None, max_length=32)
    diagnosis: str | None = Field(default=None, max_length=512)


class UpdateBillItemsRequest(BaseModel):
    model_config = _STRICT

    items: list[BillItemInput] = Field(min_length=1, max_length=MAX_ITEMS)
    metadata: BillMetadataInput | None = None
    context: BillContextInput | None = None
    mark_confirmed: bool = True


class PreviewItemInput(BillItemInput):
    """One row of the review table on its way to a live, unsaved comparison.

    Two differences from :class:`BillItemInput`, both because the review screen
    posts the whole table rather than a finished bill:

    * ``description`` may be empty, so blank rows travel with the rest and the
      response can be mapped back to the row the user is still typing into.
    * ``key`` is the client's row key, echoed back as the comparison ``id``,
      so adding or removing a row above never mis-assigns a status.
    """

    model_config = _STRICT

    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)
    key: str = Field(min_length=1, max_length=64)


class BillItemOut(ORMModel):
    id: str
    position: int
    description: str
    category: str
    service_name: str | None = None
    quantity: float
    unit_price: float
    total_price: float
    confidence: float
    is_user_verified: bool
    user_edited: bool
    needs_confirmation: bool
    source: str
    notes: str | None = None


class BillTotalsOut(BaseModel):
    items_total: float
    subtotal: float
    taxes_total: float
    discounts_total: float
    insurance_deduction: float
    grand_total: float
    stated_grand_total: float | None = None
    total_mismatch: bool = False
    mismatch_amount: float = 0.0


class ExtractionMetaOut(BaseModel):
    provider: str = "demo"
    is_real_provider: bool = False
    method: str = "deterministic"
    ocr_used: bool = False
    text_length: int = 0
    low_confidence_items: int = 0
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class BillOut(ORMModel):
    id: str
    status: str
    source: str
    is_demo: bool
    hospital_name: str | None = None
    hospital_location: str | None = None
    city: str | None = None
    country: str | None = None
    hospital_category: str | None = None
    treatment: str | None = None
    room_category: str | None = None
    patient_name: str | None = None
    patient_id: str | None = None
    bill_number: str | None = None
    bill_date: date | None = None
    admission_date: date | None = None
    discharge_date: date | None = None
    length_of_stay_days: int | None = None
    diagnosis: str | None = None
    subtotal: float | None = None
    taxes_total: float | None = None
    discounts_total: float | None = None
    insurance_deduction: float | None = None
    grand_total: float | None = None
    stated_grand_total: float | None = None
    currency_code: str = "INR"
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[BillItemOut] = Field(default_factory=list)
    totals: BillTotalsOut
    extraction: ExtractionMetaOut
    has_analysis: bool = False


class UploadResponse(BaseModel):
    bill: BillOut
    next_step: str = "extract"
    warnings: list[str] = Field(default_factory=list)


class ExtractResponse(BaseModel):
    bill: BillOut
    warnings: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True


class ManualBillCreateRequest(BaseModel):
    """Escape hatch when a document cannot be read at all."""

    model_config = _STRICT

    metadata: BillMetadataInput = Field(default_factory=BillMetadataInput)
    context: BillContextInput = Field(default_factory=BillContextInput)
    items: list[BillItemInput] = Field(min_length=1, max_length=MAX_ITEMS)


class RedactionOptions(BaseModel):
    hide_patient_name: bool = True
    hide_patient_id: bool = True
    hide_bill_number: bool = True
    hide_hospital_name: bool = False
    include_questions: bool = True
    include_sources: bool = True


# --- enumerations exposed to the frontend --------------------------------


class CategoryOption(BaseModel):
    value: str
    label: str


class EnumOptionsResponse(BaseModel):
    categories: list[CategoryOption]
    hospital_categories: list[CategoryOption]
    room_categories: list[CategoryOption]
    cities: list[str]
    countries: list[CategoryOption] = Field(default_factory=list)
    treatments: list[str]
    demo_scenarios: list["DemoScenarioInfo"] = Field(default_factory=list)


class DemoScenarioInfo(BaseModel):
    key: str
    title: str
    description: str
    expectation: str
    is_demo_data: bool = True


EnumOptionsResponse.model_rebuild()
