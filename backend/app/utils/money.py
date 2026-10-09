"""Deterministic monetary arithmetic helpers.

All money in the system is handled as Decimal-free floats rounded to 2 dp at
explicit boundaries. Benchmark statistics and percentage math live here so
that they are testable in isolation and never depend on an AI provider.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import math

CENT = 0.01

#: Display symbols per ISO currency code. Unknown codes fall back to the code
#: itself so an amount is never shown with another currency's symbol.
CURRENCY_SYMBOLS: dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "AUD": "A$",
    "EUR": "€",
    "GBP": "£",
    "CAD": "C$",
    "SGD": "S$",
    "NZD": "NZ$",
    "JPY": "¥",
    "CNY": "¥",
}


def symbol_for_currency(code: str | None) -> str:
    """Display symbol for an ISO currency code (``AUD`` -> ``A$``)."""
    if not code:
        return "₹"
    return CURRENCY_SYMBOLS.get(code.strip().upper(), code.strip().upper() + " ")


def round_money(value: float | int | None) -> float:
    """Round to 2 decimal places using half-up (money) semantics."""
    if value is None:
        return 0.0
    return float(round(float(value) + 1e-9, 2))


def safe_div(numerator: float, denominator: float) -> float | None:
    """Division that returns ``None`` instead of raising/NaN on zero."""
    if denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def percentage_of(value: float, base: float) -> float | None:
    """``value`` expressed as a percentage of ``base`` (rounded to 1 dp)."""
    result = safe_div(value, base)
    if result is None:
        return None
    return round(result * 100, 1)


def percentage_difference(actual: float, reference: float) -> float | None:
    """Signed percentage difference of ``actual`` relative to ``reference``.

    ``(actual - reference) / reference * 100``. Positive means the bill amount
    is above the reference figure. Returns ``None`` when the reference is zero
    because the percentage would be undefined and misleading.
    """
    if reference == 0:
        return None
    result = (actual - reference) / reference * 100
    if math.isnan(result) or math.isinf(result):
        return None
    return round(result, 1)


def percentage_above_upper_bound(actual: float, upper_bound: float) -> float | None:
    """How far ``actual`` sits above ``upper_bound``, as a positive percentage."""
    if upper_bound <= 0:
        return None
    return round(max(0.0, (actual - upper_bound) / upper_bound * 100), 1)


def percentage_below_lower_bound(actual: float, lower_bound: float) -> float | None:
    """How far ``actual`` sits below ``lower_bound``, as a positive percentage."""
    if lower_bound <= 0:
        return None
    return round(max(0.0, (lower_bound - actual) / lower_bound * 100), 1)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sum_money(values: Iterable[float | None]) -> float:
    return round_money(sum(v for v in values if v is not None))


def sum_bounds(bounds: Sequence[tuple[float, float] | None]) -> tuple[float | None, float | None]:
    """Sum a sequence of ``(min, max)`` pairs, ignoring incomplete pairs."""
    lows = [b[0] for b in bounds if b is not None and b[0] is not None]
    highs = [b[1] for b in bounds if b is not None and b[1] is not None]
    if not lows or not highs:
        return (None, None)
    return (round_money(sum(lows)), round_money(sum(highs)))


def _signed(amount: float, magnitude_body: str, symbol: str, with_symbol: bool) -> str:
    """Accounting-style negatives: ``-₹2,700`` rather than ``₹-2,700``.

    ``magnitude_body`` must be built from ``abs(amount)``; this helper owns the
    sign so it is never applied twice.
    """
    prefix = f"-{symbol}" if amount < 0 else (symbol if with_symbol else "")
    return f"{prefix}{magnitude_body}"


def format_money(amount: float | None, symbol: str = "₹", *, with_symbol: bool = True) -> str:
    """Full-precision display form, e.g. ``₹1,94,500``, ``₹950`` or ``-₹12,000``.

    Sub-rupee precision is dropped: every amount in this system is rounded to
    two decimal places at write time, so showing paise in the UI is noise.
    """
    if amount is None:
        return "—"
    value = abs(amount)
    if value >= 10000000:
        return _signed(amount, f"{value / 10000000:.2f}Cr", symbol, with_symbol)
    if value >= 100000:
        return _signed(amount, f"{value / 100000:.2f}L", symbol, with_symbol)
    return _signed(amount, f"{value:,.0f}", symbol, with_symbol)


def format_range_money(
    low: float | None, high: float | None, symbol: str = "₹", separator: str = " – "
) -> str:
    """Render a ``min – max`` range with both ends at one consistent scale.

    Formatting each end independently produced output such as
    ``₹ 800.00 – ₹ 1,150``; ranges are only meaningful when the two figures
    share a unit and precision.
    """
    if low is None and high is None:
        return "—"
    if low is None or high is None:
        return f"{format_money(low, symbol)}{separator}{format_money(high, symbol)}"
    magnitude = max(abs(low), abs(high))
    if magnitude >= 100000:
        return (
            f"{_signed(low, f'{abs(low) / 100000:.2f}L', symbol, True)}{separator}"
            f"{_signed(high, f'{abs(high) / 100000:.2f}L', symbol, True)}"
        )
    return f"{format_money(low, symbol)}{separator}{format_money(high, symbol)}"


def format_compact(amount: float | None, symbol: str = "₹") -> str:
    """Axis-friendly short form used by charts."""
    if amount is None:
        return "—"
    prefix = symbol
    value = abs(amount)
    if value >= 10000000:
        return f"{prefix}{amount / 10000000:.1f}Cr"
    if value >= 100000:
        return f"{prefix}{amount / 100000:.1f}L"
    if value >= 1000:
        return f"{prefix}{amount / 1000:.1f}k"
    return f"{prefix}{amount:.0f}"


def format_percent(value: float | None, *, signed: bool = True) -> str:
    if value is None:
        return "—"
    if signed and value > 0:
        return f"+{value:.1f}%"
    return f"{value:.1f}%"
