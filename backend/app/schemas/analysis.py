"""Pydantic schemas for analysis results and reporting."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bill import MAX_ITEMS, BillContextInput, PreviewItemInput
from app.schemas.common import ORMModel


class BenchmarkRangeOut(BaseModel):
    min: float | None = None
    median: float | None = None
    max: float | None = None
    display: str = "—"
    available: bool = False


class ChargeComparisonOut(ORMModel):
    id: str
    bill_item_id: str | None = None
    sort_index: int = 0
    description: str
    category: str
    quantity: float
    actual_amount: float

    matched_service_name: str | None = None
    match_score: float = 0.0
    match_reason: str | None = None
    match_scope: str | None = None

    benchmark_min: float | None = None
    benchmark_median: float | None = None
    benchmark_max: float | None = None
    benchmark_unit_price_median: float | None = None
    benchmark_display: str = "—"
    benchmark_available: bool = False

    difference_from_median: float | None = None
    percentage_difference: float | None = None
    percentage_above_max: float | None = None
    percentage_below_min: float | None = None
    difference_display: str = "—"

    flag_status: str
    flag_label: str
    flag_reason: str
    is_flagged: bool

    source_name: str | None = None
    source_url: str | None = None
    source_date: date | None = None
    verification_status: str | None = None
    dataset_label: str | None = None

    ai_explanation: str | None = None
    ai_questions: list[str] = Field(default_factory=list)
    ai_explanation_source: str | None = None


class CategorySpend(BaseModel):
    category: str
    label: str
    actual: float
    benchmark_min: float | None = None
    benchmark_max: float | None = None
    difference: float | None = None
    percent_of_bill: float = 0.0
    has_benchmark: bool = False


class ChartData(BaseModel):
    category_spend: list[CategorySpend] = Field(default_factory=list)
    actual_vs_benchmark: list[dict] = Field(default_factory=list)


class AnalysisCounts(BaseModel):
    analyzed: int = 0
    within_range: int = 0
    below_range: int = 0
    above_range: int = 0
    review: int = 0
    attention: int = 0
    insufficient_data: int = 0
    not_comparable: int = 0


class AnalysisTotals(BaseModel):
    bill_total: float
    comparable_subtotal: float
    benchmark_min_total: float | None = None
    benchmark_median_total: float | None = None
    benchmark_max_total: float | None = None
    difference_min: float | None = None
    difference_max: float | None = None
    difference_display: str = "—"
    benchmark_display: str = "—"
    coverage_percent: float = 0.0


class AnalysisContextOut(BaseModel):
    city: str | None = None
    country: str | None = None
    hospital_category: str | None = None
    treatment: str | None = None
    room_category: str | None = None


class PreviewRequest(BaseModel):
    """The review screen's current, unsaved charges, for a live comparison.

    Separate from ``UpdateBillItemsRequest`` because nothing here is written:
    the point of the review screen is that the user corrects the bill first,
    and the flags are what they correct against.
    """

    model_config = ConfigDict(extra="forbid")

    bill_id: str | None = Field(default=None, max_length=64)
    items: list[PreviewItemInput] = Field(min_length=1, max_length=MAX_ITEMS)
    context: BillContextInput | None = None


class PreviewResponse(BaseModel):
    bill_id: str | None = None
    comparisons: list[ChargeComparisonOut] = Field(default_factory=list)
    counts: AnalysisCounts = Field(default_factory=AnalysisCounts)
    coverage_percent: float = 0.0
    headline: str = ""
    dataset_label: str
    is_demo_data: bool = False
    notices: list[str] = Field(default_factory=list)
    disclaimer: str
    context: AnalysisContextOut = Field(default_factory=AnalysisContextOut)


class AnalysisOut(BaseModel):
    id: str
    bill_id: str
    status: str
    created_at: datetime
    context: AnalysisContextOut
    totals: AnalysisTotals
    counts: AnalysisCounts
    comparisons: list[ChargeComparisonOut] = Field(default_factory=list)
    flagged: list[ChargeComparisonOut] = Field(default_factory=list)
    chart_data: ChartData = Field(default_factory=ChartData)
    questions: list[str] = Field(default_factory=list)
    summary: str | None = None
    headline: str | None = None
    dataset_label: str
    is_demo_data: bool
    provider_name: str
    provider_is_real: bool
    thresholds: dict = Field(default_factory=dict)
    engine_version: str = "1.0.0"
    disclaimer: str
    notices: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    analysis: AnalysisOut
    messages: list[str] = Field(default_factory=list)


class ReportRequest(BaseModel):
    hide_patient_name: bool = True
    hide_patient_id: bool = True
    hide_bill_number: bool = True
    hide_hospital_name: bool = False
    include_questions: bool = True
    include_sources: bool = True
    format: str = Field(default="json", pattern="^(json|html|markdown)$")


class ReportResponse(BaseModel):
    bill_id: str
    generated_at: datetime
    anonymized: bool
    redaction_applied: dict[str, bool]
    title: str
    sections: list[dict]
    disclaimer: str
    dataset_notice: str
    ai_notice: str
    provider_name: str
    provider_is_real: bool
    markdown: str | None = None
    html: str | None = None
    chart_data: ChartData | None = None
