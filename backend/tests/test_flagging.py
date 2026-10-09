"""Flag thresholds and benchmark matching.

Flagging decides what a user is told to look at, so every boundary is pinned
down here. All of it is deterministic: the AI provider is never involved.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.enums import ChargeCategory, FlagStatus
from app.services.benchmark_matching import is_benchmarkable_category, should_scale
from app.services.flagging import evaluate, headline_for, thresholds_snapshot


def _evaluate(actual, low, high, median, *, benchmarkable=True, has_match=True, config=None):
    return evaluate(
        actual_amount=actual,
        benchmark_min=low,
        benchmark_median=median,
        benchmark_max=high,
        benchmarkable=benchmarkable,
        has_match=has_match,
        config=config,
    )


class TestFlagThresholds:
    def test_within_range_when_below_maximum(self):
        flag = _evaluate(1_000, 800.0, 1_200.0, 1_000.0)
        assert flag.status == FlagStatus.WITHIN_RANGE.value
        assert flag.is_flagged is False

    def test_exactly_at_maximum_is_not_above(self):
        flag = _evaluate(1_200, 800.0, 1_200.0, 1_000.0)
        assert flag.status == FlagStatus.WITHIN_RANGE.value

    def test_ten_percent_over_maximum_is_review(self):
        flag = _evaluate(1_320, 800.0, 1_200.0, 1_000.0)
        assert flag.status == FlagStatus.REVIEW.value
        assert flag.is_flagged is True

    def test_twenty_five_percent_over_maximum_is_attention(self):
        flag = _evaluate(1_500, 800.0, 1_200.0, 1_000.0)
        assert flag.status == FlagStatus.ATTENTION.value
        assert flag.is_flagged is True

    def test_status_depends_on_upper_bound_not_median(self):
        # 900 is 80% above the median but inside the range: it is not a flag.
        flag = _evaluate(1_150, 800.0, 1_200.0, 500.0)
        assert flag.status == FlagStatus.WITHIN_RANGE.value

    def test_substantially_below_is_reported_as_below_range(self):
        flag = _evaluate(600, 800.0, 1_200.0, 1_000.0)
        assert flag.status == FlagStatus.BELOW_RANGE.value
        assert flag.is_flagged is False

    def test_slightly_below_is_within_range(self):
        flag = _evaluate(780, 800.0, 1_200.0, 1_000.0)
        assert flag.status == FlagStatus.WITHIN_RANGE.value

    def test_thresholds_are_configurable(self):
        # 1_250 is 4.2% above the 1_200 maximum: below the default 10% review
        # threshold, but attention once the thresholds are tightened.
        strict = Settings(flag_review_pct=1.0, flag_attention_pct=2.0)
        assert _evaluate(1_250, 800.0, 1_200.0, 1_000.0).status == FlagStatus.WITHIN_RANGE.value
        assert _evaluate(1_250, 800.0, 1_200.0, 1_000.0, config=strict).status == (
            FlagStatus.ATTENTION.value
        )

    def test_thresholds_snapshot_records_the_config_used(self):
        snapshot = thresholds_snapshot(Settings(flag_review_pct=7.5))
        assert snapshot["review_pct"] == 7.5
        assert set(snapshot) == {
            "review_pct",
            "attention_pct",
            "within_tolerance_pct",
            "min_significant_difference",
            "min_records",
        }


class TestInsufficientData:
    def test_missing_match_is_not_treated_as_a_flag(self):
        flag = _evaluate(9_000, None, None, None, has_match=False)
        assert flag.status == FlagStatus.INSUFFICIENT_DATA.value
        assert flag.is_flagged is False
        assert "benchmark" in flag.reason.lower()

    def test_non_clinical_lines_are_not_comparable(self):
        flag = _evaluate(500, None, None, None, benchmarkable=False)
        assert flag.status == FlagStatus.NOT_COMPARABLE.value
        assert flag.is_flagged is False

    def test_inverted_benchmark_range_is_ignored(self):
        # A corrupt record (min > max) previously made every charge look
        # "within range", the most dangerous possible failure.
        flag = _evaluate(1_000, 1_200.0, 800.0, 1_000.0)
        assert flag.status == FlagStatus.INSUFFICIENT_DATA.value
        assert flag.is_flagged is False


class TestNeutralLanguage:
    def test_reasons_avoid_accusatory_terms(self):
        for flag in (
            _evaluate(9_000, 800.0, 1_000.0, 900.0),
            _evaluate(100, 800.0, 1_000.0, 900.0),
            _evaluate(5_000, None, None, None, has_match=False),
        ):
            text = f"{flag.reason} {flag.label}".lower()
            for word in ("fraud", "scam", "illegal", "malpractice", "unlawful", "overcharg"):
                assert word not in text, f"{word!r} leaked into: {text}"

    def test_headline_is_neutral(self):
        headline = headline_for(
            {
                "attention": 2,
                "review": 1,
                "insufficient_data": 0,
                "above_range": 3,
                "analyzed": 10,
            }
        )
        assert "attention" in headline.lower() or "above" in headline.lower()
        for word in ("fraud", "scam", "illegal"):
            assert word not in headline.lower()


class TestCategoryEligibility:
    def test_clinical_categories_are_benchmarkable(self):
        assert is_benchmarkable_category(ChargeCategory.ROOM.value)
        assert is_benchmarkable_category(ChargeCategory.LABORATORY.value)
        assert is_benchmarkable_category(ChargeCategory.SURGERY.value)

    def test_adjustment_lines_are_not_benchmarkable(self):
        assert not is_benchmarkable_category(ChargeCategory.TAX.value)
        assert not is_benchmarkable_category(ChargeCategory.DISCOUNT.value)
        assert not is_benchmarkable_category(ChargeCategory.INSURANCE.value)


class _Bench:
    def __init__(self, unit: str):
        self.unit = unit


class TestQuantityScaling:
    """A per-visit benchmark must be multiplied by the number of visits.

    Regression: only ``per_*unit`` figures were scaled, so a 3-visit doctor fee
    was compared against the price of a single visit and reported as ~226%
    above benchmark.
    """

    def test_scales_for_multi_unit_lines(self):
        assert should_scale(_Bench("per_day"), 3) is True
        assert should_scale(_Bench("per_visit"), 2) is True
        assert should_scale(_Bench("per_order"), 5) is True
        assert should_scale(_Bench("per_unit"), 4) is True

    def test_does_not_scale_single_unit_lines(self):
        assert should_scale(_Bench("per_case"), 1) is False
        assert should_scale(_Bench("per_day"), 0) is False

    def test_unknown_units_are_not_scaled(self):
        assert should_scale(_Bench("per_astral_unit"), 4) is False
