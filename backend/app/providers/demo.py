"""Demo provider - fully offline, deterministic, no API key required.

This provider is *not* an AI model and never claims to be one. It uses the
rule-based parser in :mod:`app.providers.deterministic_parser` plus the
categorization rules in :mod:`app.services.categorization`, and it produces
explanations and questions from fixed templates. Everything it returns is
labelled ``method="deterministic"`` and surfaced in the UI as demo output.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.enums import CATEGORY_LABELS
from app.core.logging import get_logger
from app.providers.base import (
    AIProvider,
    Categorization,
    DocumentInput,
    ExplanationContext,
    ExtractedBill,
    ExtractedItem,
    ProviderCapabilities,
    ProviderStatus,
    SummaryContext,
    sanitize_items,
)
from app.providers.deterministic_parser import ParsedBill, parse_bill_text
from app.services.categorization import categorize, service_name_for
from app.utils.money import format_money
from app.utils.text import guard_language, truncate_words

logger = get_logger(__name__)

METHOD = "deterministic_rules"

#: Lower-case nouns used inside sentences. ``CATEGORY_LABELS`` values are proper
#: display labels ("Procedure Charges"), and lower-casing them produced awkward
#: prose such as "the procedures charge".
_CATEGORY_NOUNS: dict[str, str] = {
    "doctor": "doctor / consultant",
    "room": "room",
    "icu": "intensive care",
    "nursing": "nursing",
    "laboratory": "laboratory",
    "imaging": "imaging",
    "pharmacy": "pharmacy",
    "procedure": "procedure",
    "surgery": "surgery",
    "consumables": "consumables",
    "equipment": "equipment",
    "oxygen": "oxygen and medical gas",
    "blood_bank": "blood bank",
    "package": "treatment package",
    "miscellaneous": "miscellaneous",
    "tax": "tax",
    "discount": "discount",
    "insurance": "insurance adjustment",
}


def _noun(category: str | None, fallback: str = "charge") -> str:
    return _CATEGORY_NOUNS.get(category or "", fallback)

#: Template question bank. Keyed by category; always informational.
_QUESTION_TEMPLATES: dict[str, tuple[str, ...]] = {
    "default": (
        "Can you provide an itemised breakdown of this charge?",
        "What quantity of this item was used, and over how many days?",
        "Is this service included in the treatment package I was quoted?",
        "Are consumables and medicines billed separately from this service?",
        "Was this service performed once, or on multiple occasions?",
        "Can you explain how this amount was calculated?",
    ),
    "room": (
        "Which room category was I admitted to, and for how many nights?",
        "Is the room charge inclusive of nursing and monitoring?",
        "Was any part of my stay in a higher category than the one agreed at admission?",
        "Can you share the daily room rate that was applied?",
    ),
    "icu": (
        "How many hours or days was I in intensive care?",
        "What clinical criteria determined the ICU admission?",
        "Does the ICU charge include the monitoring equipment and nursing care?",
        "Can you provide the daily ICU rate and the total days charged?",
    ),
    "doctor": (
        "Which doctor or consultant is this professional fee for?",
        "How many visits or procedures does this fee cover?",
        "Does this include follow-up visits after discharge?",
    ),
    "laboratory": (
        "Can you list each individual test included in this laboratory charge?",
        "How many times were these tests performed during my stay?",
        "Were any of these tests repeated, and why?",
        "Were any of these tests ordered by the treating doctor?",
    ),
    "imaging": (
        "Which imaging studies does this charge cover, and how many of each?",
        "Was contrast used for this study, and is that billed separately?",
        "How many imaging sessions took place during my admission?",
    ),
    "pharmacy": (
        "Can you provide the itemised list of medicines dispensed, with quantities?",
        "How many days of medication does this quantity cover?",
        "Were any medicines provided as part of the treatment package?",
        "Were any medicines returned unused?",
    ),
    "procedure": (
        "Can you explain what this procedure involved and how the price was arrived at?",
        "Was this procedure part of the planned treatment, or was it additional?",
        "Does this charge include the consumables used during the procedure?",
        "How many times was this procedure performed?",
    ),
    "surgery": (
        "Which surgeon and team performed this operation?",
        "Does this surgical charge include the operation theatre, anaesthesia and monitoring?",
        "Was the surgical procedure part of a package, and what was the package price?",
        "Can you share the itemised breakdown of this surgical charge?",
    ),
    "consumables": (
        "Can you list the consumables billed here, with the quantity used?",
        "Were these consumables part of the surgical or procedure package?",
        "Were any of these items billed more than once?",
    ),
    "equipment": (
        "Which equipment does this charge refer to, and for how long was it used?",
        "Is equipment usage included in the room or ICU charge?",
    ),
    "nursing": (
        "Does the nursing charge cover all shifts, and is it separate from the room charge?",
        "How were nursing hours calculated for this stay?",
    ),
    "oxygen": (
        "How many hours of oxygen or medical gas were used?",
        "Is oxygen included in the room or ICU charge?",
    ),
    "blood_bank": (
        "Which blood products were provided, in what quantity?",
        "Were these products cross-matched, and how many units were kept unused?",
    ),
    "miscellaneous": (
        "Can you explain what is included in this miscellaneous charge?",
        "Is there an itemised breakdown available for this amount?",
    ),
    "discount": (
        "What discount or scheme was applied to my bill?",
        "Were additional discounts or cashless benefits available at admission?",
    ),
    "insurance": (
        "Which portion of this bill was settled by the insurer?",
        "Can you share the detailed claim settlement statement?",
    ),
    "tax": (
        "Can you confirm the tax components and rates applied to this bill?",
    ),
}

_BILL_QUESTIONS: tuple[str, ...] = (
    "Can you provide a fully itemised version of this bill, with one row per service?",
    "What was the package or estimate I was given at admission, and how does this bill differ from it?",
    "Which charges relate to the treating doctor's professional fee, and which to the hospital?",
    "Can you share a day-by-day summary of what was done and charged?",
    "Were any items billed more than once, and can the duplicate entries be explained?",
    "If any part of this bill is being revised, who should I contact and what is the timeline?",
)

_POSSIBLE_FACTORS: dict[str, tuple[str, ...]] = {
    "room": (
        "the room category actually allocated, the length of stay, and any period spent in a higher category",
        "whether the quoted category differed from the category allocated at admission",
    ),
    "icu": (
        "the number of hours or days spent in critical care and the monitoring required",
        "the specific clinical circumstances of the admission",
    ),
    "doctor": (
        "the seniority and specialisation of the consulting physician, and the number of visits",
        "whether a resident or consultant review is billed separately",
    ),
    "laboratory": (
        "the specific tests ordered, and how many times each was performed",
        "whether tests were repeated during the admission",
    ),
    "imaging": (
        "the imaging modality used and whether contrast was administered",
        "the number of imaging sessions performed",
    ),
    "pharmacy": (
        "the specific medicines dispensed and the duration they were needed for",
        "whether the medicines were supplied as part of a treatment package",
    ),
    "procedure": (
        "the complexity of the procedure and the time taken",
        "the consumables and equipment used during the procedure",
    ),
    "surgery": (
        "the operating team involved, the theatre time, and the anaesthesia used",
        "whether the operation was part of a quoted surgical package",
    ),
    "consumables": (
        "the specific consumable items and the quantity actually used",
        "whether consumables were already included in a procedure or package charge",
    ),
    "equipment": (
        "the specific equipment used and the duration of its use",
        "whether equipment is already included in the room or ICU rate",
    ),
    "nursing": (
        "the nursing shifts covered and the level of care required",
        "whether nursing is billed separately from the accommodation charge",
    ),
    "oxygen": (
        "the number of hours of oxygen or medical gas administered",
        "whether gas is included in the accommodation or critical care charge",
    ),
    "blood_bank": (
        "the number of blood units issued and how many remained unused",
        "the cross-matching and processing steps involved",
    ),
    "miscellaneous": (
        "the specific services included in this line",
        "whether the amount is a fixed administration or facility charge",
    ),
}


def _money(amount: float | None, symbol: str) -> str:
    return format_money(amount, symbol)


class DemoAIProvider(AIProvider):
    """Rule-based provider used when no external AI is configured."""

    name = "demo"
    is_real = False
    capabilities = ProviderCapabilities(
        supports_vision=False, supports_chat=False, supports_json_mode=False
    )

    # -- extraction ----------------------------------------------------
    async def extract_bill(self, document: DocumentInput) -> ExtractedBill:
        text = document.text or ""
        if not text.strip():
            return ExtractedBill(
                items=[],
                confidence=0.0,
                provider=self.name,
                method=METHOD,
                warnings=[
                    "No readable text was found in this document. The demo extractor "
                    "reads the text layer of PDFs only; it cannot OCR images."
                ],
            )

        parsed: ParsedBill = parse_bill_text(text)
        warnings = list(parsed.warnings)

        items: list[ExtractedItem] = []
        for item in parsed.items:
            category, confidence, _reason = categorize(item.description)
            items.append(
                ExtractedItem(
                    description=item.description,
                    category=category,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                    confidence=round(min(item.confidence, confidence * 0.35 + item.confidence * 0.65), 3),
                    service_name=service_name_for(item.description, category),
                )
            )

        fields = parsed.fields
        bill_date = fields.get("bill_date")
        return ExtractedBill(
            hospital_name=_as_str(fields.get("hospital_name")),
            hospital_location=_as_str(fields.get("hospital_location")),
            city=_as_str(fields.get("city")),
            patient_name=_as_str(fields.get("patient_name")),
            patient_id=_as_str(fields.get("patient_id")),
            bill_number=_as_str(fields.get("bill_number")),
            bill_date=bill_date if isinstance(bill_date, date) else None,
            admission_date=fields.get("admission_date") if isinstance(fields.get("admission_date"), date) else None,
            discharge_date=fields.get("discharge_date") if isinstance(fields.get("discharge_date"), date) else None,
            room_category=_as_str(fields.get("room_category")),
            length_of_stay_days=fields.get("length_of_stay_days") if isinstance(fields.get("length_of_stay_days"), int) else None,
            diagnosis=_as_str(fields.get("diagnosis")),
            items=items,
            stated_grand_total=fields.get("stated_grand_total") if isinstance(fields.get("stated_grand_total"), (int, float)) else None,
            confidence=parsed.confidence,
            warnings=warnings,
            provider=self.name,
            method=METHOD,
        )

    # -- categorization ------------------------------------------------
    async def classify_charge(
        self,
        description: str,
        *,
        category_hint: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Categorization:
        category, confidence, reason = categorize(description, hint=category_hint)
        return Categorization(
            category=category,
            confidence=confidence,
            service_name=service_name_for(description, category),
            reason=reason,
            source="rules",
        )

    # -- language ------------------------------------------------------
    async def explain_difference(self, context: ExplanationContext) -> str:
        symbol = "₹"
        label = _noun(context.category)
        parts: list[str] = []

        if not context.benchmark_max:
            return (
                f"No reliable benchmark record was found for this {label} "
                f"in the selected comparison set, so no comparison was made. That is a "
                f"gap in the available data, not an indication that the charge is high "
                f"or low."
            )

        amount = _money(context.actual_amount, symbol)
        above_max = context.percentage_above_max
        span = f"{_money(context.benchmark_min, symbol)} to {_money(context.benchmark_max, symbol)}"

        if above_max and above_max > 0:
            parts.append(
                f"The {label} charge of {amount} is approximately {above_max:.1f}% "
                f"above the upper end of the available benchmark range "
                f"({span}, benchmark median "
                f"{_money(context.benchmark_median, symbol)})."
            )
        elif context.percentage_difference and context.percentage_difference > 0:
            parts.append(
                f"The {label} charge of {amount} is approximately "
                f"{context.percentage_difference:.1f}% above the benchmark median "
                f"({_money(context.benchmark_median, symbol)}), but it still sits "
                f"within the benchmark range of {span}."
            )
        else:
            parts.append(
                f"The {label} charge of {amount} falls within the available "
                f"benchmark range of {span}."
            )

        parts.append(
            "This comparison does not establish that the charge is incorrect. "
            "Benchmark ranges come from a limited set of records and cannot account "
            "for every situation."
        )

        factors = _POSSIBLE_FACTORS.get(context.category, ())
        if factors:
            joined = "; ".join(factors)
            parts.append(
                f"Possible factors that may explain the difference include {joined}. "
                f"These are possibilities, not confirmed reasons - only the hospital "
                f"can confirm what applied to your case."
            )

        if context.matched_service_name:
            parts.append(
                f"The comparison used the benchmark record for "
                f"\u201c{context.matched_service_name}\u201d"
                + (f" from {context.source_name}." if context.source_name else ".")
            )

        return guard_language(truncate_words(" ".join(parts), 150))[0]

    async def generate_questions(
        self, context: ExplanationContext, *, scope: str = "charge"
    ) -> list[str]:
        if scope == "bill":
            return list(_BILL_QUESTIONS)
        base = _QUESTION_TEMPLATES.get(context.category, _QUESTION_TEMPLATES["default"])
        label = _noun(context.category, "this charge")
        questions = [
            f"Regarding the {label} charge of {_money(context.actual_amount, '₹')}, "
            f"can you provide an itemised breakdown?",
            *base[:3],
            "What quantity of this item was used, and over how many days?",
        ]
        seen: set[str] = set()
        result: list[str] = []
        for question in questions:
            cleaned, _ = guard_language(question)
            key = cleaned.lower()
            if key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result[:6]

    async def summarize_bill(self, context: SummaryContext) -> str:
        symbol = "₹"
        sentences: list[str] = [
            f"Your bill totals {_money(context.bill_total, symbol)}."
        ]

        if context.benchmark_min_total is not None and context.benchmark_max_total is not None:
            sentences.append(
                f"Based on the available benchmark records, the estimated range for the "
                f"charges that could be compared is "
                f"{_money(context.benchmark_min_total, symbol)} to "
                f"{_money(context.benchmark_max_total, symbol)}."
            )
            if context.coverage_percent is not None and context.coverage_percent < 100:
                sentences.append(
                    f"Benchmark records were only available for {context.coverage_percent:.0f}% "
                    f"of the comparable charges on this bill, so this range does not cover "
                    f"the whole bill and the remaining charges are unassessed."
                )
            if context.difference_max and context.difference_max > 0:
                low = _money(context.difference_min, symbol)
                high = _money(context.difference_max, symbol)
                subject = (
                    "the comparable charges"
                    if (context.coverage_percent or 0) < 100
                    else "your bill"
                )
                if low == high:
                    sentences.append(f"That is a difference of {high} for {subject}.")
                elif (context.difference_min or 0) < 0:
                    sentences.append(
                        f"For {subject}, the total is as much as "
                        f"{_money(abs(context.difference_min or 0.0), symbol)} below "
                        f"the lower end of the benchmark range, and as much as {high} "
                        f"above the upper end."
                    )
                else:
                    sentences.append(
                        f"For {subject}, the difference against the benchmark range is "
                        f"approximately {low} to {high}."
                    )
        else:
            sentences.append(
                "There is not enough benchmark information available to estimate a "
                "comparable range for this bill."
            )

        if context.items_analyzed:
            above = context.items_above_range
            sentences.append(
                f"{context.items_analyzed} charges were compared; "
                f"{above} of them {'sits' if above == 1 else 'sit'} above the available "
                f"benchmark range and {context.items_insufficient_data} could not be "
                f"compared because sufficient benchmark data was not available."
            )

        if context.top_flagged:
            names = ", ".join(name for name, _label, _pct in context.top_flagged[:3])
            sentences.append(
                f"The largest contributors to the difference are: {names}."
            )

        sentences.append(
            "This comparison does not establish that any charge was incorrect. Consider "
            "requesting itemised explanations for the highlighted charges before you pay."
        )

        return guard_language(" ".join(sentences))[0]

    async def health(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            is_real=False,
            ready=True,
            detail=(
                "Deterministic rule-based demo provider. No AI model is used and no "
                "network calls are made."
            ),
        )


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["DemoAIProvider", "sanitize_items"]
