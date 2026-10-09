"""Deterministic benchmark matching.

Pure Python. No AI. No network. The same inputs always produce the same
comparison, which is what makes the numbers in a MedBill Lens report
auditable and unit-testable.

Matching is deliberately conservative: a benchmark record is only used when it
is a *reasonable* comparable, and when no such record exists the result is
"no sufficient benchmark data available" rather than a guess.

Comparison tiers, applied in order:

1. ``exact``                 - service name, category, room type and treatment
                               scope all compatible.
2. ``treatment_relaxed``     - record is not scoped to a treatment.
3. ``room_agnostic``         - record carries no room scope at all, so it
                               applies regardless of the patient's room type.
4. ``no match``              - report insufficient data. Nothing is estimated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from app.core.config import Settings, settings
from app.core.enums import (
    NON_BENCHMARK_CATEGORIES,
    RoomCategory,
    VerificationStatus,
)
from app.utils.text import combined_match_score, keyword_score, normalize_text, similarity

SCOPE_EXACT = "exact"
SCOPE_TREATMENT_RELAXED = "treatment_relaxed"
SCOPE_ROOM_AGNOSTIC = "room_agnostic"
SCOPE_ROOM_RELAXED = "room_relaxed"
#: Used by the engine (not by ``find_match`` itself) when no record for the
#: bill's own hospital type resembles the charge, but a record for the same
#: city under a different hospital type does. The row keeps its own source
#: and verification status, so the comparison stays labelled honestly.
SCOPE_HOSPITAL_RELAXED = "hospital_category_relaxed"

#: Only these categories are meaningfully scoped by the patient's room type.
#: (The room dimension of a *bill line* is the ICU type, which is tracked on the
#: record itself, so the patient's ward category is not applied to it.)
ROOM_SENSITIVE_CATEGORIES: frozenset[str] = frozenset({"room"})

CRITICAL_CARE_ROOMS: frozenset[str] = frozenset(
    {
        RoomCategory.ICU.value,
        RoomCategory.NICU.value,
        RoomCategory.PICU.value,
        RoomCategory.CCU.value,
        RoomCategory.EMERGENCY.value,
    }
)

#: Unit labels kept for provenance/display. Scaling does not depend on the unit:
#: a benchmark figure is multiplied by the bill line's quantity whenever that
#: quantity is greater than 1, because the line total then represents N
#: units of the service (N days, N visits, N studies, N units).
SCALING_UNITS: frozenset[str] = frozenset(
    {
        "per_unit", "per_day", "per_night", "per_study", "per_session",
        "per_item", "per_visit", "per_order", "per_case", "per_test",
    }
)


@dataclass(slots=True)
class ComparableQuery:
    description: str
    service_name: str | None
    category: str
    city: str | None
    hospital_category: str | None
    treatment: str | None
    room_category: str | None
    quantity: float = 1.0


@dataclass(slots=True)
class BenchmarkMatch:
    benchmark: object  # app.models.BenchmarkPrice
    match_score: float
    scope: str
    reason: str
    considered: int = 1
    ranked: list[tuple[float, str, object]] = field(default_factory=list)


@dataclass(slots=True)
class NoMatch:
    reason: str
    scope: str | None = None
    considered: int = 0


def room_related(a: str | None, b: str | None) -> bool:
    if not a and not b:
        return True
    if not a or not b:
        return False
    if normalize_text(a) == normalize_text(b):
        return True
    return normalize_text(a) in CRITICAL_CARE_ROOMS and normalize_text(b) in CRITICAL_CARE_ROOMS


def room_compatible(category: str, query_room: str | None, record_room: str | None) -> bool:
    """Should a record's room scope be considered compatible with the bill line?"""
    if record_room is None:
        return True  # room-agnostic record: applies to any accommodation
    if not query_room:
        return True  # the user has not told us the room type
    if normalize_text(query_room) == normalize_text(record_room):
        return True
    if category == "icu":
        # ICU subtypes (ICU / NICU / PICU / CCU) are compared together.
        return room_related(query_room, record_room)
    if category in ROOM_SENSITIVE_CATEGORIES:
        return False
    return True


def treatment_compatible(record_treatment: str | None, wanted: str | None) -> bool:
    if not record_treatment or not wanted:
        return True
    return combined_match_score(wanted, record_treatment) >= 0.4


def description_score(description: str | None, service_name: str | None) -> float:
    """Best of the three scorers, each computed once.

    ``combined_match_score`` is itself ``max(similarity, keyword_score)``, so
    calling it alongside the two scorers would run ``similarity`` (the expensive
    one) twice per comparison for an identical result.
    """
    score_similarity = similarity(description, service_name)
    score_keyword = keyword_score(description, service_name)
    return max(score_similarity, score_keyword)


def find_match(
    records: Iterable,
    query: ComparableQuery,
    config: Settings | None = None,
) -> BenchmarkMatch | NoMatch:
    """Select the single most comparable benchmark record for a charge.

    ``records`` is an iterable of ``BenchmarkPrice`` rows that already passed
    the city / hospital-category filter.
    """
    config = config or settings
    candidates = list(records)

    if not candidates:
        return NoMatch(
            reason="No benchmark records exist for this city and hospital category."
        )

    threshold = config.benchmark_service_similarity_threshold

    def category_ok(record) -> bool:
        return not (query.category and record.service_category and query.category != record.service_category)

    def score_for(record) -> float:
        return max(
            description_score(query.service_name, record.service_name),
            description_score(query.description, record.service_name),
        )

    scored = [(score_for(r), r) for r in candidates if category_ok(r)]
    scored = [(s, r) for s, r in scored if s >= threshold]

    if not scored:
        return NoMatch(
            reason=(
                "No benchmark service in this city and hospital category resembles this "
                f"charge closely enough (minimum similarity {threshold:.0%})."
            ),
            considered=len(candidates),
        )

    # --- tier 1: fully comparable --------------------------------------
    exact = [
        (s, r)
        for s, r in scored
        if room_compatible(query.category, query.room_category, r.room_category)
        and treatment_compatible(r.treatment, query.treatment)
    ]
    if exact:
        exact.sort(key=lambda t: (-t[0], t[1].service_name))
        return _build_match(exact, SCOPE_EXACT, "Matched on service, category and comparison context")

    # --- tier 2: record is not scoped to a treatment ---------------------
    treatment_relaxed = [
        (s, r)
        for s, r in scored
        if room_compatible(query.category, query.room_category, r.room_category)
    ]
    if treatment_relaxed:
        treatment_relaxed.sort(key=lambda t: (-t[0], t[1].service_name))
        return _build_match(
            treatment_relaxed,
            SCOPE_TREATMENT_RELAXED,
            "Closest available service match (not limited to a specific treatment)",
        )

    # --- tier 3: room-agnostic records -----------------------------------
    room_agnostic = [(s, r) for s, r in scored if not r.room_category]
    if room_agnostic:
        room_agnostic.sort(key=lambda t: (-t[0], t[1].service_name))
        return _build_match(
            room_agnostic,
            SCOPE_ROOM_AGNOSTIC,
            "Closest available service match (benchmark record has no room category)",
        )

    # --- tier 4: same room type but only when the user gave none ---------
    if not query.room_category:
        return NoMatch(reason="No comparable benchmark service was found.", considered=len(candidates))

    return NoMatch(
        reason=(
            "Benchmark records exist for this service, but none match the selected "
            f"room category ('{query.room_category}'). Comparison across different room "
            "categories is not meaningful."
        ),
        considered=len(candidates),
    )


def _build_match(
    ranked: Sequence[tuple[float, object]], scope: str, reason: str
) -> BenchmarkMatch:
    best_score, best = ranked[0]
    return BenchmarkMatch(
        benchmark=best,
        match_score=round(best_score, 3),
        scope=scope,
        reason=reason,
        considered=len(ranked),
        ranked=[(round(s, 3), r.service_name, r) for s, r in ranked[:5]],  # type: ignore[union-attr]
    )


def is_benchmarkable_category(category: str) -> bool:
    return category not in NON_BENCHMARK_CATEGORIES


def should_scale(record, quantity: float) -> bool:
    """Whether a benchmark figure applies *per unit* of the bill line.

    Only quantities greater than one need scaling; multiplying by one is a
    no-op that would otherwise be reported as a scaled comparison.
    """
    if not quantity or quantity <= 1:
        return False
    return (record.unit or "") in SCALING_UNITS


def verification_note(status: str) -> str:
    if status == VerificationStatus.DEMO.value:
        return "Demo Benchmark Dataset — illustrative values, not real-world prices."
    if status == VerificationStatus.GOVERNMENT_RATE.value:
        return "Government-published rate."
    if status == VerificationStatus.PUBLISHED_TARIFF.value:
        return "Published hospital tariff."
    if status == VerificationStatus.OFFICIAL_DATASET.value:
        return "Official public dataset."
    if status == VerificationStatus.VERIFIED_THIRD_PARTY.value:
        return "Verified third-party source."
    return "Unverified source — treat with caution."
