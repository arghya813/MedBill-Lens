"""AI provider abstraction.

Design contract
---------------
An :class:`AIProvider` is only ever allowed to influence:

  * document understanding / field extraction
  * charge categorization
  * natural-language explanations
  * question generation

It is **never** allowed to produce or influence benchmark ranges, price
comparisons, percentage differences, flag thresholds or any other numerical
result. Those are computed deterministically in ``app.services.benchmark_engine``
and ``app.services.flagging`` and are unit-tested without any provider.

Implementations live in sibling modules and are resolved by
:mod:`app.providers.registry` from environment configuration.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Value objects passed to / returned by providers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DocumentInput:
    """A document handed to a provider.

    ``content_bytes`` is the raw upload and is what the deterministic text
    extractor reads (pypdf for PDFs, the OCR engine for images). ``text`` is
    filled in from it before any provider is called.

    ``image_bytes`` is deliberately *separate* and is only populated for raster
    uploads. Vision-capable providers must attach real image payloads, so PDF
    bytes must never end up in this field - doing that produces a broken
    ``data:image/png`` part containing a PDF.
    """

    filename: str
    content_type: str
    size_bytes: int
    text: str = ""
    content_bytes: bytes | None = None
    image_bytes: bytes | None = None
    kind: str = "pdf"  # pdf | image
    hints: dict[str, Any] = field(default_factory=dict)

    @property
    def bytes_for_extraction(self) -> bytes | None:
        """Raw bytes the text extractor should read."""
        return self.content_bytes or self.image_bytes


@dataclass(slots=True)
class ExtractedItem:
    description: str
    category: str
    quantity: float = 1.0
    unit_price: float = 0.0
    total_price: float = 0.0
    confidence: float = 0.5
    service_name: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "category": self.category,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "confidence": self.confidence,
            "service_name": self.service_name,
            "notes": self.notes,
        }


@dataclass(slots=True)
class ExtractedBill:
    """Structured bill produced by a provider."""

    hospital_name: str | None = None
    hospital_location: str | None = None
    city: str | None = None
    patient_name: str | None = None
    patient_id: str | None = None
    bill_number: str | None = None
    bill_date: date | None = None
    admission_date: date | None = None
    discharge_date: date | None = None
    room_category: str | None = None
    length_of_stay_days: int | None = None
    diagnosis: str | None = None
    items: list[ExtractedItem] = field(default_factory=list)
    stated_grand_total: float | None = None
    confidence: float = 0.5
    warnings: list[str] = field(default_factory=list)
    provider: str = "demo"
    method: str = "deterministic"
    used_vision: bool = False

    @property
    def is_usable(self) -> bool:
        return bool(self.items)


@dataclass(slots=True)
class Categorization:
    category: str
    confidence: float = 0.5
    service_name: str | None = None
    reason: str | None = None
    source: str = "rules"


@dataclass(slots=True)
class ExplanationContext:
    """Everything an LLM needs to *describe* a comparison in words.

    Note what is absent: the provider is given the already-computed numbers as
    read-only context. It is asked to explain, not to calculate.
    """

    description: str
    category: str
    category_label: str
    quantity: float
    actual_amount: float
    benchmark_min: float | None
    benchmark_median: float | None
    benchmark_max: float | None
    percentage_above_max: float | None
    percentage_difference: float | None
    flag_status: str
    flag_label: str
    matched_service_name: str | None
    city: str | None
    hospital_category: str | None
    treatment: str | None
    room_category: str | None
    source_name: str | None
    dataset_label: str


@dataclass(slots=True)
class SummaryContext:
    hospital_name: str | None
    bill_total: float
    benchmark_min_total: float | None
    benchmark_max_total: float | None
    difference_min: float | None
    difference_max: float | None
    items_analyzed: int
    items_within_range: int
    items_above_range: int
    items_insufficient_data: int
    coverage_percent: float | None = None
    top_flagged: list[tuple[str, str, float | None]] = field(default_factory=list)
    city: str | None = None
    hospital_category: str | None = None
    treatment: str | None = None
    dataset_label: str = ""


@dataclass(slots=True)
class ProviderStatus:
    name: str
    is_real: bool
    ready: bool
    detail: str


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class AIProvider(abc.ABC):
    """Abstract AI / OCR provider.

    Concrete providers must be side-effect free with respect to the database
    and must never raise for recoverable problems: they should raise
    :class:`app.core.errors.ProviderError` so the fallback layer can act.
    """

    name: str = "base"
    is_real: bool = False

    # -- document understanding -------------------------------------
    @abc.abstractmethod
    async def extract_bill(self, document: DocumentInput) -> ExtractedBill:
        """Extract structured fields and line items from a bill document."""

    async def classify_charge(
        self,
        description: str,
        *,
        category_hint: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Categorization:
        """Suggest a category for a single charge description."""
        raise NotImplementedError

    # -- language tasks ----------------------------------------------
    @abc.abstractmethod
    async def explain_difference(self, context: ExplanationContext) -> str:
        """Explain, in plain language, why a charge was flagged."""

    @abc.abstractmethod
    async def generate_questions(
        self, context: ExplanationContext, *, scope: str = "charge"
    ) -> list[str]:
        """Generate respectful, informational questions for the hospital."""

    @abc.abstractmethod
    async def summarize_bill(self, context: SummaryContext) -> str:
        """Short plain-English summary of the whole analysis."""

    # -- operational -------------------------------------------------
    async def health(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            is_real=self.is_real,
            ready=True,
            detail="No health probe implemented",
        )

    async def aclose(self) -> None:  # pragma: no cover - lifecycle hook
        return None


class ProviderCapabilities:
    """Static description of what a provider can do, surfaced on /api/health."""

    def __init__(self, supports_vision: bool, supports_chat: bool, supports_json_mode: bool):
        self.supports_vision = supports_vision
        self.supports_chat = supports_chat
        self.supports_json_mode = supports_json_mode

    def to_dict(self) -> dict[str, bool]:
        return {
            "supports_vision": self.supports_vision,
            "supports_chat": self.supports_chat,
            "supports_json_mode": self.supports_json_mode,
        }


def sanitize_items(items: Sequence[dict]) -> list[dict]:
    """Normalize provider output defensively before it reaches the database."""
    cleaned: list[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        description = str(raw.get("description") or "").strip()
        if not description:
            continue
        try:
            quantity = float(raw.get("quantity") or 1.0)
        except (TypeError, ValueError):
            quantity = 1.0
        try:
            unit_price = float(raw.get("unit_price") or 0.0)
        except (TypeError, ValueError):
            unit_price = 0.0
        try:
            total_price = float(
                raw.get("total_price") if raw.get("total_price") is not None else quantity * unit_price
            )
        except (TypeError, ValueError):
            total_price = quantity * unit_price
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.5
        cleaned.append(
            {
                "description": description[:512],
                "category": str(raw.get("category") or "miscellaneous").lower()[:32],
                "service_name": (str(raw["service_name"])[:255] if raw.get("service_name") else None),
                "quantity": max(0.0, quantity),
                "unit_price": max(0.0, unit_price),
                "total_price": max(0.0, total_price),
                "confidence": min(1.0, max(0.0, confidence)),
                "notes": (str(raw["notes"])[:512] if raw.get("notes") else None),
            }
        )
    return cleaned
