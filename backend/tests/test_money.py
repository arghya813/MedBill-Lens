"""Deterministic money helpers.

These functions decide every number a user sees, so they are tested directly
rather than only through the API.
"""

from __future__ import annotations

import pytest

from app.utils.money import (
    clamp,
    format_compact,
    format_money,
    format_range_money,
    percentage_above_upper_bound,
    percentage_below_lower_bound,
    percentage_difference,
    percentage_of,
    round_money,
    safe_div,
    sum_bounds,
    sum_money,
)


class TestRoundAndSum:
    def test_round_money_uses_two_decimals(self):
        assert round_money(10.005) == 10.01
        assert round_money(10.004) == 10.0
        assert round_money(None) == 0.0

    def test_sum_money_ignores_none(self):
        assert sum_money([100.0, None, 50.5]) == 150.5

    def test_sum_money_is_floating_point_safe(self):
        # 0.1 + 0.2 style drift must not leak into user-facing totals.
        assert sum_money([0.1, 0.2]) == 0.3

    def test_sum_bounds_ignores_incomplete_pairs(self):
        assert sum_bounds([(1.0, 2.0), None, (3.0, 4.0)]) == (4.0, 6.0)
        assert sum_bounds([]) == (None, None)
        assert sum_bounds([(1.0, None)]) == (None, None)


class TestPercentages:
    def test_safe_div_returns_none_on_zero(self):
        assert safe_div(10, 0) is None
        assert safe_div(10, 2) == 5.0

    def test_percentage_of(self):
        assert percentage_of(25, 50) == 50.0
        assert percentage_of(25, 0) is None

    def test_percentage_difference_is_signed_relative_to_reference(self):
        assert percentage_difference(150, 100) == 50.0
        assert percentage_difference(80, 100) == -20.0
        assert percentage_difference(10, 0) is None

    def test_percentage_above_upper_bound_never_negative(self):
        assert percentage_above_upper_bound(150, 100) == 50.0
        assert percentage_above_upper_bound(80, 100) == 0.0
        assert percentage_above_upper_bound(10, 0) is None

    def test_percentage_below_lower_bound_never_negative(self):
        assert percentage_below_lower_bound(50, 100) == 50.0
        assert percentage_below_lower_bound(120, 100) == 0.0

    def test_clamp(self):
        assert clamp(5, 0, 3) == 3
        assert clamp(-5, 0, 3) == 0
        assert clamp(2, 0, 3) == 2


class TestFormatting:
    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (None, "—"),
            (0, "₹0"),
            (950, "₹950"),
            (1_200, "₹1,200"),
            (27_000, "₹27,000"),
            (118_000, "₹1.18L"),
            (2_301_000, "₹23.01L"),
        ],
    )
    def test_format_money(self, amount, expected):
        assert format_money(amount) == expected

    def test_negative_amounts_use_accounting_style(self):
        # Regression: this used to render as "₹-2,700".
        assert format_money(-2_700) == "-₹2,700"
        assert format_money(-12_000) == "-₹12,000"

    def test_format_money_without_symbol(self):
        assert format_money(1_200, with_symbol=False) == "1,200"

    def test_range_ends_share_one_scale(self):
        # Regression: independent formatting produced "₹ 800.00 – ₹ 1,150".
        assert format_range_money(800, 1_150) == "₹800 – ₹1,150"
        assert format_range_money(118_000, 175_000) == "₹1.18L – ₹1.75L"

    def test_range_with_missing_bound(self):
        assert format_range_money(None, None) == "—"
        assert format_range_money(100, None) == "₹100 – —"

    def test_compact_forms(self):
        assert format_compact(950) == "₹950"
        assert format_compact(27_000) == "₹27.0k"
        assert format_compact(194_100) == "₹1.9L"
        assert format_compact(None) == "—"
