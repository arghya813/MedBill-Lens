"""Benchmark comparison engine.

Owns every number in a MedBill Lens report. Takes a confirmed bill plus a
comparison context, produces one :class:`ChargeComparison` per comparable
charge and a set of whole-bill totals.

Guarantees:
  * No AI provider is involved anywhere in this file.
  * If a benchmark does not exist for a charge, nothing is estimated.
  * Ranges are reported as ranges, never as a single "correct" price.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.enums import (
    ADDITIVE_CATEGORIES,
    CREDIT_CATEGORIES,
    DatasetLabel,
    FlagStatus,
    TRUSTED_VERIFICATION,
)
from app.core.logging import get_logger
from app.models import BenchmarkPrice, Bill, BillItem
from app.services import benchmark_matching as matching
from app.services.benchmark_matching import BenchmarkMatch, ComparableQuery, NoMatch
from app.services.flagging import FlagResult, evaluate, headline_for, thresholds_snapshot
from app.utils.money import (
    format_money,
    format_range_money,
    percentage_difference,
    round_money,
    sum_bounds,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class ComparisonResult:
    bill_item_id: str
    description: str
    category: str
    quantity: float
    actual_amount: float

    benchmark_id: str | None = None
    matched_service_name: str | None = None
    match_score: float = 0.0
    match_reason: str = ""
    match_scope: str | None = None

    benchmark_min: float | None = None
    benchmark_median: float | None = None
    benchmark_max: float | None = None
    benchmark_unit_price_median: float | None = None

    difference_from_median: float | None = None
    percentage_difference: float | None = None
    percentage_above_max: float | None = None
    percentage_below_min: float | None = None

    flag: FlagResult = field(default_factory=lambda: FlagResult(
        status=FlagStatus.INSUFFICIENT_DATA.value,
        label="No sufficient benchmark data",
        reason="No benchmark was evaluated.",
        is_flagged=False,
    ))

    source_name: str | None = None
    source_url: str | None = None
    source_date: date | None = None
    verification_status: str | None = None
    dataset_label: str | None = None


@dataclass(slots=True)
class EngineTotals:
    bill_total: float = 0.0
    comparable_subtotal: float = 0.0
    benchmark_min_total: float | None = None
    benchmark_median_total: float | None = None
    benchmark_max_total: float | None = None
    difference_min: float | None = None
    difference_max: float | None = None
    coverage_percent: float = 0.0
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class EngineOutcome:
    results: list[ComparisonResult]
    totals: EngineTotals
    headline: str
    city: str | None
    hospital_category: str | None
    treatment: str | None
    room_category: str | None
    dataset_label: str
    all_demo: bool
    used_verified_sources: bool
    thresholds: dict
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Repository access
# ---------------------------------------------------------------------------


def load_candidate_records(
    db: Session,
    *,
    city: str | None,
    hospital_category: str | None,
    country_code: str | None = None,
    currency_code: str | None = None,
    config: Settings | None = None,
) -> list[BenchmarkPrice]:
    """Records from the same city / hospital type, with documented fallbacks.

    ``currency_code`` is applied whenever it is known: comparing a bill denominated
    in one currency against rates published in another would produce a number that
    looks authoritative and is meaningless. ``country_code`` narrows further when
    the bill states one; it is what keeps two countries sharing a currency (or a
    city name) from comparing against each other.
    """
    config = config or settings
    statements = []
    currency = BenchmarkPrice.currency_code == currency_code if currency_code else None
    country = BenchmarkPrice.country_code == country_code if country_code else None

    def _with(stmt):
        if currency is not None:
            stmt = stmt.where(currency)
        if country is not None:
            stmt = stmt.where(country)
        return stmt

    if city and hospital_category:
        statements.append(
            _with(
                select(BenchmarkPrice).where(
                    BenchmarkPrice.city == city,
                    BenchmarkPrice.hospital_category == hospital_category,
                )
            )
        )
    if city and not hospital_category:
        statements.append(_with(select(BenchmarkPrice).where(BenchmarkPrice.city == city)))
    if hospital_category and not city:
        statements.append(
            _with(
                select(BenchmarkPrice).where(
                    BenchmarkPrice.hospital_category == hospital_category
                )
            )
        )
    if not city and not hospital_category:
        statements.append(_with(select(BenchmarkPrice)))

    records: dict[str, BenchmarkPrice] = {}
    for statement in statements:
        for record in db.scalars(statement):
            records[record.id] = record
    return list(records.values())


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _scale_benchmark_for_quantity(
    record: BenchmarkPrice, quantity: float
) -> tuple[float, float, float, float | None]:
    """Convert a per-unit benchmark into a line total where appropriate.

    A room benchmark quoted "per day" must be multiplied by the number of days
    on the bill, otherwise the comparison is meaningless.
    """
    if matching.should_scale(record, quantity):
        multiplier = quantity
        unit_median = record.median_price
    else:
        multiplier = 1.0
        unit_median = None
    return (
        round_money(record.min_price * multiplier),
        round_money(record.median_price * multiplier),
        round_money(record.max_price * multiplier),
        round_money(unit_median) if unit_median is not None else None,
    )


def analyze_bill(
    db: Session,
    bill: Bill,
    *,
    config: Settings | None = None,
) -> EngineOutcome:
    config = config or settings

    city = bill.city or None
    hospital_category = bill.hospital_category or None
    treatment = bill.treatment or None
    room_category = bill.room_category or None
    country = getattr(bill, "country", None) or None
    currency = (
        getattr(bill, "currency_code", None) or config.currency_code or None
    )

    records = load_candidate_records(
        db,
        city=city,
        hospital_category=hospital_category,
        country_code=country,
        currency_code=currency,
        config=config,
    )
    by_category: dict[str, list[BenchmarkPrice]] = {}
    for record in records:
        by_category.setdefault(record.service_category, []).append(record)

    # Same-city records under a different hospital type. Only consulted for a
    # charge that finds nothing among its own hospital type's records, so
    # every comparison that already matched keeps exactly the record it had.
    # This is what lets a private-hospital bill compare against the published
    # CGHS tariff (labelled as such on the row) instead of reporting no data.
    fallback_by_category: dict[str, list[BenchmarkPrice]] = {}
    if city and hospital_category:
        for record in load_candidate_records(
            db,
            city=city,
            hospital_category=None,
            country_code=country,
            currency_code=currency,
            config=config,
        ):
            if record.hospital_category == hospital_category:
                continue
            fallback_by_category.setdefault(record.service_category, []).append(record)

    results: list[ComparisonResult] = []
    notes: list[str] = []
    used_fallback = False

    if not records:
        notes.append(
            "No benchmark records are available for the selected city and hospital "
            "category, so no comparison could be made for this bill."
        )

    for item in sorted(bill.items, key=lambda i: i.position):
        result = _compare_item(
            item,
            by_category,
            city,
            hospital_category,
            treatment,
            room_category,
            config,
            currency_code=currency,
            fallback_by_category=fallback_by_category,
        )
        used_fallback = used_fallback or result.match_scope == matching.SCOPE_HOSPITAL_RELAXED
        results.append(result)

    if used_fallback:
        notes.append(
            "For some charges no comparable benchmark existed for this hospital type, "
            "so records from the same city's other hospital types were used. Each "
            "affected row shows its own source."
        )

    totals = _compute_totals(results, bill, config)
    headline = headline_for(totals.counts)

    all_demo = all(
        (r.verification_status or "demo") not in TRUSTED_VERIFICATION for r in results if r.benchmark_id
    ) or not results
    used_verified = any(
        (r.verification_status or "") in TRUSTED_VERIFICATION for r in results if r.benchmark_id
    )
    if all_demo and not used_verified:
        notes.append(
            "All benchmark values used in this comparison come from the demo dataset "
            "and are illustrative only."
        )

    return EngineOutcome(
        results=results,
        totals=totals,
        headline=headline,
        city=city,
        hospital_category=hospital_category,
        treatment=treatment,
        room_category=room_category,
        dataset_label=DatasetLabel.DEMO.value if all_demo else "Verified public benchmark records",
        all_demo=all_demo,
        used_verified_sources=used_verified,
        thresholds=thresholds_snapshot(config),
        notes=notes,
    )


def _compare_item(
    item: BillItem,
    by_category: dict[str, list[BenchmarkPrice]],
    city: str | None,
    hospital_category: str | None,
    treatment: str | None,
    room_category: str | None,
    config: Settings,
    currency_code: str | None = None,
    fallback_by_category: dict[str, list[BenchmarkPrice]] | None = None,
) -> ComparisonResult:
    actual = round_money(item.total_price)
    benchmarkable = item.category in ADDITIVE_CATEGORIES
    query = ComparableQuery(
        description=item.description,
        service_name=item.service_name or item.description,
        category=item.category,
        city=city,
        hospital_category=hospital_category,
        treatment=treatment,
        room_category=room_category,
        quantity=item.quantity,
    )

    result = ComparisonResult(
        bill_item_id=item.id,
        description=item.description,
        category=item.category,
        quantity=item.quantity,
        actual_amount=actual,
    )

    if not benchmarkable:
        result.flag = evaluate(
            actual_amount=actual,
            benchmark_min=None,
            benchmark_median=None,
            benchmark_max=None,
            benchmarkable=False,
            has_match=False,
            currency_code=currency_code,
            config=config,
        )
        return result

    candidates = by_category.get(item.category, [])
    outcome: BenchmarkMatch | NoMatch = matching.find_match(candidates, query, config)

    if isinstance(outcome, NoMatch) and (fallback_by_category or {}).get(item.category):
        fallback = matching.find_match(
            fallback_by_category[item.category], query, config
        )
        if isinstance(fallback, BenchmarkMatch):
            fallback.scope = matching.SCOPE_HOSPITAL_RELAXED
            fallback.reason = (
                "Closest comparable service in the same city from a different "
                "hospital type; the row shows its own source."
            )
            outcome = fallback

    if isinstance(outcome, NoMatch):
        result.flag = evaluate(
            actual_amount=actual,
            benchmark_min=None,
            benchmark_median=None,
            benchmark_max=None,
            benchmarkable=True,
            has_match=False,
            match_reason=outcome.reason,
            currency_code=currency_code,
            config=config,
        )
        result.match_reason = outcome.reason
        return result

    record = outcome.benchmark
    if record.record_count < config.benchmark_min_records:
        result.flag = evaluate(
            actual_amount=actual,
            benchmark_min=None,
            benchmark_median=None,
            benchmark_max=None,
            benchmarkable=True,
            has_match=False,
            match_reason=(
                f"The closest available benchmark has only {record.record_count} supporting "
                f"record(s), below the configured minimum of {config.benchmark_min_records}."
            ),
            currency_code=currency_code,
            config=config,
        )
        result.match_reason = result.flag.reason
        return result

    lo, median, hi, unit_median = _scale_benchmark_for_quantity(record, item.quantity)
    result.benchmark_id = record.id
    result.matched_service_name = record.service_name
    result.match_score = outcome.match_score
    result.match_reason = outcome.reason
    result.match_scope = outcome.scope
    result.benchmark_min = lo
    result.benchmark_median = median
    result.benchmark_max = hi
    result.benchmark_unit_price_median = unit_median
    result.source_name = record.source_name
    result.source_url = record.source_url
    result.source_date = record.source_date
    result.verification_status = record.verification_status
    result.dataset_label = record.dataset_label

    result.flag = evaluate(
        actual_amount=actual,
        benchmark_min=lo,
        benchmark_median=median,
        benchmark_max=hi,
        benchmarkable=True,
        has_match=True,
        match_reason=outcome.reason,
        currency_code=currency_code,
        config=config,
    )
    result.difference_from_median = result.flag.difference_from_median
    result.percentage_difference = result.flag.percentage_difference
    result.percentage_above_max = result.flag.percentage_above_max
    result.percentage_below_min = result.flag.percentage_below_min
    return result


def _compute_totals(
    results: list[ComparisonResult], bill: Bill, config: Settings
) -> EngineTotals:
    counts = {
        "analyzed": 0,
        "within_range": 0,
        "below_range": 0,
        "review": 0,
        "attention": 0,
        "insufficient_data": 0,
        "not_comparable": 0,
        "above_range": 0,
    }

    comparable_subtotal = 0.0
    bounds: list[tuple[float, float] | None] = []
    medians: list[float] = []
    mins: list[float] = []
    maxes: list[float] = []

    for result in results:
        if result.category in CREDIT_CATEGORIES:
            counts["not_comparable"] += 1
            continue
        if result.category not in ADDITIVE_CATEGORIES:
            counts["not_comparable"] += 1
            continue

        if result.flag.status == FlagStatus.ATTENTION.value:
            counts["attention"] += 1
            counts["above_range"] += 1
        elif result.flag.status == FlagStatus.REVIEW.value:
            counts["review"] += 1
            counts["above_range"] += 1
        elif result.flag.status == FlagStatus.WITHIN_RANGE.value:
            counts["within_range"] += 1
        elif result.flag.status == FlagStatus.BELOW_RANGE.value:
            counts["below_range"] += 1
        elif result.flag.status == FlagStatus.INSUFFICIENT_DATA.value:
            counts["insufficient_data"] += 1
        else:
            counts["not_comparable"] += 1

        if result.benchmark_min is not None and result.benchmark_max is not None:
            bounds.append((result.benchmark_min, result.benchmark_max))
            mins.append(result.benchmark_min)
            medians.append(result.benchmark_median or 0.0)
            maxes.append(result.benchmark_max)
            # Only charges that actually have a benchmark figure may enter the
            # comparable subtotal. Including uncovered charges would compare the
            # whole bill against a range built from a handful of line items and
            # produce a wildly misleading headline difference.
            comparable_subtotal += result.actual_amount

    counts["analyzed"] = len(
        [r for r in results if r.category in ADDITIVE_CATEGORIES]
    )

    bill_total = round_money(bill.grand_total if bill.grand_total is not None else comparable_subtotal)
    comparable_subtotal = round_money(comparable_subtotal)

    if bounds:
        bench_min, bench_max = sum_bounds(bounds)
        bench_median = round_money(sum(medians))
        # The reported comparable range applies to the same set of charges as
        # the comparable subtotal, so the difference is meaningful.
        diff_min = round_money(comparable_subtotal - bench_max) if bench_max is not None else None
        diff_max = round_money(comparable_subtotal - bench_min) if bench_min is not None else None
        coverage = round(len(bounds) / max(1, counts["analyzed"]) * 100, 1)
    else:
        bench_min = bench_median = bench_max = None
        diff_min = diff_max = None
        coverage = 0.0

    return EngineTotals(
        bill_total=bill_total,
        comparable_subtotal=comparable_subtotal,
        benchmark_min_total=bench_min,
        benchmark_median_total=bench_median,
        benchmark_max_total=bench_max,
        difference_min=diff_min,
        difference_max=diff_max,
        coverage_percent=coverage,
        counts=counts,
    )


def format_range(lo: float | None, hi: float | None, symbol: str = "₹") -> str:
    if lo is None or hi is None:
        return "No sufficient benchmark data available."
    return format_range_money(lo, hi, symbol)


def format_difference(diff_min: float | None, diff_max: float | None, symbol: str = "₹") -> str:
    if diff_min is None or diff_max is None:
        return "Not available"
    if abs(diff_min - diff_max) < 1:
        return format_money(diff_min, symbol)
    return format_range_money(min(diff_min, diff_max), max(diff_min, diff_max), symbol)


def total_percentage(comparable_subtotal: float, benchmark_median: float | None) -> float | None:
    return percentage_difference(comparable_subtotal, benchmark_median or 0)
