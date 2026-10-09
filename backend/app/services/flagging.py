"""Transparent, rules-based flagging.

Deterministic and configurable via environment variables. The four outcomes
are deliberately neutral:

* ``within_range``      - the charge sits inside the published band
* ``below_range``       - the charge sits below the published band
* ``review``            - moderately above the band
* ``attention``         - substantially above the band
* ``insufficient_data`` - no usable benchmark exists
* ``not_comparable``    - the category is not benchmarked (tax, discount, ...)

No outcome in this module ever describes a bill or a hospital as wrong,
unlawful, or fraudulent, and no AI provider is consulted.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, settings
from app.core.enums import FlagStatus, FLAG_LABELS
from app.utils.money import (
    format_money,
    percentage_above_upper_bound,
    percentage_below_lower_bound,
    round_money,
    symbol_for_currency,
)

STATUS_NOT_COMPARABLE_REASON = (
    "This category is an accounting entry rather than a billable clinical service, "
    "so it is not compared against service benchmarks."
)
STATUS_NO_BENCHMARK_REASON = "No sufficient benchmark data available."


@dataclass(slots=True)
class FlagResult:
    status: str
    label: str
    reason: str
    is_flagged: bool
    difference_from_median: float | None = None
    percentage_difference: float | None = None
    percentage_above_max: float | None = None
    percentage_below_min: float | None = None


def thresholds_snapshot(config: Settings | None = None) -> dict:
    config = config or settings
    return {
        "review_pct": config.flag_review_pct,
        "attention_pct": config.flag_attention_pct,
        "within_tolerance_pct": config.flag_within_tolerance_pct,
        "min_significant_difference": config.min_significant_difference,
        "min_records": config.benchmark_min_records,
    }


def evaluate(
    *,
    actual_amount: float,
    benchmark_min: float | None,
    benchmark_median: float | None,
    benchmark_max: float | None,
    benchmarkable: bool,
    has_match: bool,
    match_reason: str = "",
    currency_code: str | None = None,
    config: Settings | None = None,
) -> FlagResult:
    config = config or settings
    symbol = symbol_for_currency(currency_code or config.currency_code)

    if not benchmarkable:
        return FlagResult(
            status=FlagStatus.NOT_COMPARABLE.value,
            label=FLAG_LABELS[FlagStatus.NOT_COMPARABLE.value],
            reason=STATUS_NOT_COMPARABLE_REASON,
            is_flagged=False,
        )

    if not has_match or benchmark_min is None or benchmark_median is None or benchmark_max is None:
        return FlagResult(
            status=FlagStatus.INSUFFICIENT_DATA.value,
            label=FLAG_LABELS[FlagStatus.INSUFFICIENT_DATA.value],
            reason=f"{STATUS_NO_BENCHMARK_REASON} {match_reason}".strip(),
            is_flagged=False,
        )

    if benchmark_min > benchmark_max:
        # A corrupt benchmark row would otherwise make every charge look
        # "within range", which is the most dangerous possible failure here.
        return FlagResult(
            status=FlagStatus.INSUFFICIENT_DATA.value,
            label=FLAG_LABELS[FlagStatus.INSUFFICIENT_DATA.value],
            reason=(
                f"{STATUS_NO_BENCHMARK_REASON} The matched benchmark record has an "
                f"invalid range and was ignored."
            ),
            is_flagged=False,
        )

    difference = round_money(actual_amount - benchmark_median)
    pct_above_max = percentage_above_upper_bound(actual_amount, benchmark_max)
    pct_below_min = percentage_below_lower_bound(actual_amount, benchmark_min)
    from app.utils.money import percentage_difference

    pct_vs_median = percentage_difference(actual_amount, benchmark_median)

    materially_above = pct_above_max is not None and pct_above_max > 0
    if materially_above:
        # Compare against the *upper* bound, not the median: a charge inside the
        # published band is not "above benchmark" no matter where the median sits.
        if pct_above_max >= config.flag_attention_pct:
            reason = (
                f"This charge is approximately {pct_above_max:.1f}% above the upper end of "
                f"the available benchmark range "
                f"({format_money(benchmark_min, symbol)}–{format_money(benchmark_max, symbol)}). "
                f"It may be worth requesting an itemised explanation."
            )
            return FlagResult(
                status=FlagStatus.ATTENTION.value,
                label=FLAG_LABELS[FlagStatus.ATTENTION.value],
                reason=reason,
                is_flagged=True,
                difference_from_median=difference,
                percentage_difference=pct_vs_median,
                percentage_above_max=pct_above_max,
                percentage_below_min=pct_below_min,
            )
        if pct_above_max >= config.flag_review_pct:
            reason = (
                f"This charge is approximately {pct_above_max:.1f}% above the upper end of "
                f"the available benchmark range "
                f"({format_money(benchmark_min, symbol)}–{format_money(benchmark_max, symbol)}). "
                f"Requesting an itemised breakdown is reasonable."
            )
            return FlagResult(
                status=FlagStatus.REVIEW.value,
                label=FLAG_LABELS[FlagStatus.REVIEW.value],
                reason=reason,
                is_flagged=True,
                difference_from_median=difference,
                percentage_difference=pct_vs_median,
                percentage_above_max=pct_above_max,
                percentage_below_min=pct_below_min,
            )

    if actual_amount < benchmark_min and (pct_below_min or 0) > config.flag_review_pct:
        reason = (
            f"This charge is approximately {pct_below_min:.1f}% below the lower end of the "
            f"available benchmark range. Lower charges can indicate a package, a "
            f"negotiated rate, or a billing split across categories."
        )
        return FlagResult(
            status=FlagStatus.BELOW_RANGE.value,
            label=FLAG_LABELS[FlagStatus.BELOW_RANGE.value],
            reason=reason,
            is_flagged=False,
            difference_from_median=difference,
            percentage_difference=pct_vs_median,
            percentage_above_max=0.0,
            percentage_below_min=pct_below_min,
        )

    if abs(difference) < config.min_significant_difference and not materially_above:
        reason = (
            f"This charge is within the available benchmark range of "
            f"{format_money(benchmark_min, symbol)}–{format_money(benchmark_max, symbol)}."
        )
    else:
        reason = (
            f"This charge is within the available benchmark range of "
            f"{format_money(benchmark_min, symbol)}–{format_money(benchmark_max, symbol)} "
            f"(benchmark median {format_money(benchmark_median, symbol)})."
        )
    return FlagResult(
        status=FlagStatus.WITHIN_RANGE.value,
        label=FLAG_LABELS[FlagStatus.WITHIN_RANGE.value],
        reason=reason,
        is_flagged=False,
        difference_from_median=difference,
        percentage_difference=pct_vs_median,
        percentage_above_max=pct_above_max,
        percentage_below_min=pct_below_min,
    )


def headline_for(counts: dict) -> str:
    """A neutral one-line summary of the comparison outcome."""
    attention = counts.get("attention", 0)
    review = counts.get("review", 0)
    insufficient = counts.get("insufficient_data", 0)
    total = counts.get("analyzed", 0)

    if attention + review == 0 and insufficient == 0:
        return (
            f"All {total} compared charges fall within the available benchmark ranges. "
            f"No benchmark comparison indicates a charge that needs review."
        )
    if attention + review == 0:
        return (
            f"No compared charge sits above the available benchmark range, but "
            f"{insufficient} could not be compared because benchmark data was "
            f"unavailable."
        )
    parts = []
    if attention:
        parts.append(f"{attention} substantially above")
    if review:
        parts.append(f"{review} moderately above")
    joined = " and ".join(parts)
    tail = (
        f", and {insufficient} could not be compared because benchmark data was unavailable."
        if insufficient
        else "."
    )
    return (
        f"Benchmark comparison indicates {joined} the available benchmark range"
        f"{tail} Requesting itemised explanations for these charges is reasonable."
    )
