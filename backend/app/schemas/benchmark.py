"""Pydantic schemas for the benchmark dataset and comparison context."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class BenchmarkPriceOut(ORMModel):
    id: str
    city: str
    city_tier: str
    country_code: str = "IN"
    hospital_category: str
    service_name: str
    service_category: str
    room_category: str | None = None
    treatment: str | None = None
    unit: str
    min_price: float
    median_price: float
    max_price: float
    record_count: int
    currency_code: str
    source_name: str
    source_url: str | None = None
    source_date: date | None = None
    verification_status: str
    dataset_label: str
    notes: str | None = None


class BenchmarkQuery(BaseModel):
    city: str | None = None
    country_code: str | None = None
    hospital_category: str | None = None
    service_category: str | None = None
    treatment: str | None = None
    room_category: str | None = None
    verified_only: bool = False
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class BenchmarkListResponse(BaseModel):
    items: list[BenchmarkPriceOut]
    total: int
    limit: int
    offset: int
    dataset_label: str
    is_demo_data: bool
    notice: str


class DatasetStatsResponse(BaseModel):
    dataset_label: str
    is_demo_data: bool
    total_records: int
    verified_records: int
    demo_records: int
    cities: list[str]
    hospital_categories: list[str]
    service_categories: list[str]
    sources: list[str]
    min_source_date: date | None = None
    max_source_date: date | None = None
    notice: str
