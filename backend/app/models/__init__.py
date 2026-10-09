"""SQLAlchemy ORM models.

Data is deliberately split into three layers so that the demo can show a
clear separation of concerns:

  1. ``RawDocument``  - the uploaded file bytes (transient, auto-deleted).
  2. ``Bill`` + children - structured bill data (PII minimised by default).
  3. ``Analysis`` + children - anonymous benchmark findings, no PII at all.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BillStatus
from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# --------------------------------------------------------------------------
# Layer 1 - raw document (transient)
# --------------------------------------------------------------------------
class RawDocument(Base, TimestampMixin):
    """The uploaded file. Never exposed over HTTP; deleted on a timer."""

    __tablename__ = "raw_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bill_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("bills.id", ondelete="CASCADE"), nullable=True, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # Extracted text is also transient and purged together with the file.
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bill: Mapped["Bill | None"] = relationship(back_populates="documents")


# --------------------------------------------------------------------------
# Layer 2 - structured bill data
# --------------------------------------------------------------------------
class Bill(Base, TimestampMixin):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(32), default=BillStatus.UPLOADED.value, index=True)
    source: Mapped[str] = mapped_column(String(32), default="upload")  # upload | demo | manual

    hospital_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hospital_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional owner-supplied context used to find comparable benchmarks.
    city: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hospital_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    treatment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    room_category: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # PII - optional, user-controlled, redacted in shared reports.
    patient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bill_number: Mapped[str | None] = mapped_column(String(120), nullable=True)

    bill_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    discharge_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    length_of_stay_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(String(512), nullable=True)

    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    taxes_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    discounts_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    insurance_deduction: Mapped[float | None] = mapped_column(Float, nullable=True)
    grand_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    stated_grand_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    currency_code: Mapped[str] = mapped_column(String(8), default="INR")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extraction_meta: Mapped[dict] = mapped_column(JSON, default=dict)

    items: Mapped[list["BillItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="BillItem.position"
    )
    documents: Mapped[list[RawDocument]] = relationship(back_populates="bill", cascade="all, delete-orphan")
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="bill", cascade="all, delete-orphan", uselist=False
    )


class BillItem(Base, TimestampMixin):
    __tablename__ = "bill_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bill_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("bills.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(512))
    category: Mapped[str] = mapped_column(String(32), default="miscellaneous", index=True)
    service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="extraction")  # extraction | user
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)

    bill: Mapped[Bill] = relationship(back_populates="items")


# --------------------------------------------------------------------------
# Benchmark data
# --------------------------------------------------------------------------
class BenchmarkPrice(Base, TimestampMixin):
    """A single price observation / price band for a comparable service.

    Designed to accept verified real-world datasets later. Every row carries
    its provenance (``source_name`` / ``source_url`` / ``source_date``) and a
    ``verification_status`` that controls how it may be presented.
    """

    __tablename__ = "benchmark_prices"
    __table_args__ = (
        UniqueConstraint("city", "hospital_category", "service_name", name="uq_benchmark_key"),
        Index("ix_benchmark_lookup", "city", "hospital_category", "service_category"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    city: Mapped[str] = mapped_column(String(120), index=True)
    city_tier: Mapped[str] = mapped_column(String(16), default="tier2")  # tier1 | tier2 | tier3
    country_code: Mapped[str] = mapped_column(String(8), default="IN", index=True)
    hospital_category: Mapped[str] = mapped_column(String(32), index=True)
    service_name: Mapped[str] = mapped_column(String(255))
    service_category: Mapped[str] = mapped_column(String(32), index=True)
    room_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    treatment: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    unit: Mapped[str] = mapped_column(String(32), default="per_unit")

    min_price: Mapped[float] = mapped_column(Float)
    median_price: Mapped[float] = mapped_column(Float)
    max_price: Mapped[float] = mapped_column(Float)
    record_count: Mapped[int] = mapped_column(Integer, default=1)
    currency_code: Mapped[str] = mapped_column(String(8), default="INR")

    source_name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="demo", index=True)
    dataset_label: Mapped[str] = mapped_column(String(255), default="Demo Benchmark Dataset")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# --------------------------------------------------------------------------
# Layer 3 - anonymous analysis results (no PII)
# --------------------------------------------------------------------------
class Analysis(Base, TimestampMixin):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bill_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("bills.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(default="completed")

    # Comparison context (non-identifying)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hospital_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    treatment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    room_category: Mapped[str | None] = mapped_column(String(32), nullable=True)

    bill_total: Mapped[float] = mapped_column(Float, default=0.0)
    comparable_subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark_min_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_median_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_max_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    difference_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    difference_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_percent: Mapped[float] = mapped_column(Float, default=0.0)

    items_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    items_within_range: Mapped[int] = mapped_column(Integer, default=0)
    items_below_range: Mapped[int] = mapped_column(Integer, default=0)
    items_review: Mapped[int] = mapped_column(Integer, default=0)
    items_attention: Mapped[int] = mapped_column(Integer, default=0)
    items_insufficient_data: Mapped[int] = mapped_column(Integer, default=0)
    items_not_comparable: Mapped[int] = mapped_column(Integer, default=0)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dataset_label: Mapped[str] = mapped_column(String(255), default="Demo Benchmark Dataset")
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=True)
    provider_name: Mapped[str] = mapped_column(String(64), default="demo")
    provider_is_real: Mapped[bool] = mapped_column(Boolean, default=False)
    thresholds: Mapped[dict] = mapped_column(JSON, default=dict)
    engine_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    bill: Mapped[Bill] = relationship(back_populates="analysis")
    results: Mapped[list["ChargeComparison"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="ChargeComparison.sort_index",
    )


class ChargeComparison(Base, TimestampMixin):
    """Deterministic per-charge comparison result. AI never writes these numbers."""

    __tablename__ = "charge_comparisons"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    analysis_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    bill_item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sort_index: Mapped[int] = mapped_column(Integer, default=0)

    description: Mapped[str] = mapped_column(String(512))
    category: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    actual_amount: Mapped[float] = mapped_column(Float, default=0.0)

    benchmark_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    matched_service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    match_reason: Mapped[str] = mapped_column(String(255), nullable=True)
    match_scope: Mapped[str | None] = mapped_column(String(64), nullable=True)

    benchmark_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_unit_price_median: Mapped[float | None] = mapped_column(Float, nullable=True)

    difference_from_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage_difference: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage_above_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentage_below_min: Mapped[float | None] = mapped_column(Float, nullable=True)

    flag_status: Mapped[str] = mapped_column(String(32), index=True)
    flag_label: Mapped[str] = mapped_column(String(64))
    flag_reason: Mapped[str] = mapped_column(Text, nullable=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Sources shown to the user so the comparison is auditable.
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dataset_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # AI-authored (language only, no numbers).
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_questions: Mapped[list] = mapped_column(JSON, default=list)
    ai_explanation_source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    analysis: Mapped[Analysis] = relationship(back_populates="results")


class QuestionSet(Base, TimestampMixin):
    __tablename__ = "question_sets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    bill_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("bills.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(32), default="bill")  # bill | charge
    charge_comparison_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    provider_name: Mapped[str] = mapped_column(String(64), default="demo")
