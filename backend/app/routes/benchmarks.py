"""Benchmark dataset endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.benchmark_repository import BenchmarkRepository
from app.schemas.benchmark import BenchmarkListResponse, BenchmarkPriceOut, DatasetStatsResponse
from app.services.seeding import benchmark_metadata

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("", response_model=BenchmarkListResponse)
def list_benchmarks(
    db: Session = Depends(get_db),
    city: str | None = Query(default=None),
    country_code: str | None = Query(default=None),
    hospital_category: str | None = Query(default=None),
    service_category: str | None = Query(default=None),
    treatment: str | None = Query(default=None),
    room_category: str | None = Query(default=None),
    verified_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Browse the benchmark dataset, including each record's source."""
    repo = BenchmarkRepository(db)
    page = repo.search(
        city=city,
        country_code=country_code,
        hospital_category=hospital_category,
        service_category=service_category,
        treatment=treatment,
        room_category=room_category,
        verified_only=verified_only,
        limit=limit,
        offset=offset,
    )
    meta = benchmark_metadata(db)
    # Reflect the records actually returned rather than hard-coding the flag:
    # a caller filtering with verified_only=true must not be told the results
    # are synthetic.
    page_is_demo = all(
        (record.verification_status or "demo") == "demo" for record in page.records
    )
    return BenchmarkListResponse(
        items=[BenchmarkPriceOut.model_validate(r) for r in page.records],
        total=page.total,
        limit=limit,
        offset=offset,
        dataset_label=meta["dataset_label"],
        is_demo_data=page_is_demo if page.records else repo.count_verified() == 0,
        notice=meta["notice"],
    )


@router.get("/stats", response_model=DatasetStatsResponse)
def benchmark_stats(
    db: Session = Depends(get_db), config: Settings = Depends(get_settings)
):
    repo = BenchmarkRepository(db)
    stats = repo.stats()
    meta = benchmark_metadata(db)
    total = repo.count()
    verified = repo.count_verified()
    return DatasetStatsResponse(
        dataset_label=meta["dataset_label"],
        is_demo_data=verified == 0,
        total_records=total,
        verified_records=verified,
        demo_records=total - verified,
        cities=stats["cities"],
        hospital_categories=stats["hospital_categories"],
        service_categories=stats["service_categories"],
        sources=stats["sources"],
        min_source_date=stats["min_source_date"],
        max_source_date=stats["max_source_date"],
        notice=meta["notice"],
    )


@router.get("/{benchmark_id}", response_model=BenchmarkPriceOut)
def get_benchmark(benchmark_id: str, db: Session = Depends(get_db)):
    repo = BenchmarkRepository(db)
    record = repo.get(benchmark_id)
    if record is None:
        from app.core.errors import MedBillError

        error = MedBillError(f"No benchmark record with id '{benchmark_id}'.")
        error.status_code = 404
        error.code = "benchmark_not_found"
        error.user_message = "We couldn't find that benchmark record."
        raise error
    return BenchmarkPriceOut.model_validate(record)
