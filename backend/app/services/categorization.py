"""Deterministic categorization rules.

These rules are the *floor* of the system: they always run, they are fully
testable, and an AI provider may only ever refine the result. Categorization
is a language-understanding task, not a numerical one, which is why it is
allowed to be model-assisted.
"""

from __future__ import annotations

from app.core.enums import ChargeCategory
from app.utils.text import normalize_text

#: (category, [keywords], base_confidence)
#: Ordered from most specific to most general: the first category with a
#: matching keyword wins, so `icu` beats `room` and `lab` beats `misc`.
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...], float], ...] = (
    (
        ChargeCategory.ICU.value,
        (
            "icu", "intensive care", "ccu", "critical care", "nicu", "picu",
            "micro care", "neonatal intensive", "ventilator support", "sicu",
        ),
        0.92,
    ),
    (
        ChargeCategory.SURGERY.value,
        (
            "surgery", "operation", "opd", "post operative", "post-op", "theatre",
            "ot charges", "surgeon", "anaesthesia during surgery", "surgical",
        ),
        0.9,
    ),
    (
        ChargeCategory.PROCEDURE.value,
        (
            "procedure", "dialysis", "haemodialysis", "hemodialysis", "endoscopy",
            "bronchoscopy", "catheterisation", "catheterization", "lumbar puncture",
            "biopsy", "aspiration", "dressing", "physiotherapy", "dialysis session",
            "cath lab", "angiography", "angioplasty", "stent", "bypass",
        ),
        0.88,
    ),
    (
        ChargeCategory.IMAGING.value,
        (
            "mri", "ct scan", "ctscan", "x-ray", "xray", "x ray", "radiograph",
            "ultrasound", "usg", "sonography", "doppler", "echo", "ecg", "ekg",
            "electrocardiogram", "pet scan", "pet-ct", "mammography", "fluoroscopy",
            "radiology", "imaging", "tele-radiology", "xray room",
        ),
        0.9,
    ),
    (
        ChargeCategory.LABORATORY.value,
        (
            "laboratory", "lab ", "lab charge", "blood test", "cbc", "cbcs", "lft",
            "kft", "tsh", "hbA1c", "hba1c", "urinalysis", "stool", "culture",
            "histopathology", "cytology", "biopsy report", "pathology", "serology",
            "microbiology", "clinical pathology", "billed amount: lab",
            "complete blood count", "c reactive protein", "vitamin d",
        ),
        0.88,
    ),
    (
        ChargeCategory.BLOOD_BANK.value,
        (
            "blood bank", "blood unit", "blood bag", "packed rbc", "prbc", "plasma",
            "platelet", "whole blood", "cross match", "crossmatch", "component",
        ),
        0.9,
    ),
    (
        ChargeCategory.PHARMACY.value,
        (
            "pharmacy", "medicine", "medicines", "medication", "drug", "tab",
            "tablet", "capsule", "injection", "iv fluid", "saline", "antibiotic",
            "oral contraceptive", "dispensing", "chemist", "meds",
        ),
        0.85,
    ),
    (
        ChargeCategory.EQUIPMENT.value,
        (
            "equipment", "monitor", "ventilator", "infusion pump", "syringe pump",
            "ecmo", "defibrillator", "imaging machine", "machinery", "device usage",
            "equipment usage", "patient monitor",
        ),
        0.85,
    ),
    (
        ChargeCategory.CONSUMABLES.value,
        (
            "consumable", "consumables", "ppe", "gloves", "syringe", "needle",
            "catheter", "dressing material", "stethoscope", "bed sheet", "linen",
            "surgical gown", "mask", "cap", "tube", "cannula", "stent", "implant",
        ),
        0.84,
    ),
    (
        ChargeCategory.NURSING.value,
        (
            "nursing", "nursing care", "nurse", "ward care", "vital monitoring",
            "bedside care", "caregiver", "attendant", "nursing charges", "patient care",
            "monitoring charges", "icu nursing",
        ),
        0.87,
    ),
    (
        ChargeCategory.OXYGEN.value,
        (
            "oxygen", "medical gas", "gas charge", "nitrous", "air", "ventilator charges",
            "ventilation charge", "respiratory",
        ),
        0.85,
    ),
    (
        ChargeCategory.ROOM.value,
        (
            "room", "room charges", "room rent", "bed", "bed charges", "ward",
            "wards", "private room", "semi private", "deluxe", "general ward",
            "cabin", "hostel", "room maintenance", "ac charges", "tele bed",
        ),
        0.86,
    ),
    (
        ChargeCategory.DOCTOR.value,
        (
            "doctor", "dr.", "dr ", "consultant", "consultation", "consultancy",
            "physician", "specialist", "surgeon fee", "visiting consultant",
            "anesthetist", "anaesthetist", "anesthesiologist", "doctor fee",
            "procedure done by", "follow up charge",
        ),
        0.87,
    ),
    (
        ChargeCategory.PACKAGE.value,
        (
            "package", "package charge", "comprehensive package", "health package",
            "treatment package", "surgical package", "deluxe package", "bundled",
        ),
        0.8,
    ),
    (
        ChargeCategory.DISCOUNT.value,
        (
            "discount", "discounts", "rebate", "concession", "waiver", "promotional",
            "hospital discount", "package discount",
        ),
        0.95,
    ),
    (
        ChargeCategory.INSURANCE.value,
        (
            "insurance", "insurer", "tpa", "claim", "deduction", "insurance deduction",
            "co pay", "copay", "cashless", "third party", "policy no",
        ),
        0.9,
    ),
    (
        ChargeCategory.TAX.value,
        (
            "tax", "gst", "cgst", "sgst", "igst", "service tax", "vat", "tds",
            "taxes", "gst @", "cgst @", "sgst @",
        ),
        0.95,
    ),
    (
        ChargeCategory.MISCELLANEOUS.value,
        (
            "misc", "miscellaneous", "other charges", "sundry", "general charges",
            "registration", "admission fee", "record charges", "certificate",
            "kitchen", "diet", "laundry", "ambulance", "transfer", "attendant",
        ),
        0.7,
    ),
)

#: Canonical service names used to look up benchmarks, per category.
SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    ChargeCategory.ROOM.value: (
        "general ward", "private room", "semi private room", "deluxe room", "suite room",
    ),
    ChargeCategory.ICU.value: ("icu", "nicu", "picu", "ccu", "intensive care"),
    ChargeCategory.NURSING.value: ("nursing care", "nursing charges"),
    ChargeCategory.DOCTOR.value: ("consultant fee", "doctor consultation", "surgeon fee"),
    ChargeCategory.LABORATORY.value: ("laboratory investigations", "pathology", "lab tests"),
    ChargeCategory.IMAGING.value: ("radiology and imaging", "imaging charges"),
    ChargeCategory.PHARMACY.value: ("pharmacy and medicines", "medicines"),
    ChargeCategory.PROCEDURE.value: ("procedure charges",),
    ChargeCategory.SURGERY.value: ("surgery charges", "operation charges"),
    ChargeCategory.CONSUMABLES.value: ("consumables",),
    ChargeCategory.EQUIPMENT.value: ("equipment and monitoring", "equipment usage"),
    ChargeCategory.OXYGEN.value: ("oxygen and medical gases",),
    ChargeCategory.BLOOD_BANK.value: ("blood bank",),
    ChargeCategory.MISCELLANEOUS.value: ("miscellaneous charges",),
}

_CATEGORY_LABELS = {
    ChargeCategory.ROOM.value: "room category",
    ChargeCategory.ICU.value: "critical care category",
    ChargeCategory.DOCTOR.value: "professional fee",
    ChargeCategory.LABORATORY.value: "laboratory service",
    ChargeCategory.IMAGING.value: "imaging service",
    ChargeCategory.PHARMACY.value: "pharmacy item",
    ChargeCategory.PROCEDURE.value: "procedure",
    ChargeCategory.SURGERY.value: "surgical service",
    ChargeCategory.CONSUMABLES.value: "consumable",
    ChargeCategory.EQUIPMENT.value: "equipment item",
    ChargeCategory.NURSING.value: "nursing service",
    ChargeCategory.OXYGEN.value: "gas service",
    ChargeCategory.BLOOD_BANK.value: "blood product",
    ChargeCategory.MISCELLANEOUS.value: "miscellaneous item",
}


def categorize(description: str, *, hint: str | None = None) -> tuple[str, float, str]:
    """Deterministic category guess.

    Returns ``(category, confidence, reason)``. Always returns a valid
    :class:`ChargeCategory` value, defaulting to ``miscellaneous``.
    """
    text = f" {normalize_text(description)} "
    if not text.strip():
        return ChargeCategory.MISCELLANEOUS.value, 0.2, "empty description"

    best: tuple[str, float, str] | None = None
    for category, keywords, base_confidence in CATEGORY_RULES:
        for keyword in keywords:
            needle = normalize_text(keyword)
            if not needle:
                continue
            if f" {needle} " in text or text.strip() == needle or text.startswith(f"{needle} "):
                confidence = base_confidence
                if hint and hint.lower() == category:
                    confidence = min(0.99, confidence + 0.05)
                candidate = (category, confidence, f"keyword '{keyword.strip()}'")
                if best is None or candidate[1] > best[1]:
                    best = candidate
                break

    if best is None:
        return ChargeCategory.MISCELLANEOUS.value, 0.35, "no rule matched; defaulted to miscellaneous"

    if hint and hint.lower() == best[0]:
        return best[0], min(0.99, best[1] + 0.05), f"{best[2]}; confirmed by document"
    return best


def service_name_for(description: str, category: str) -> str | None:
    """Best-effort canonical service label for benchmark matching."""
    text = normalize_text(description)
    for alias in SERVICE_ALIASES.get(category, ()):  # explicit alias wins
        alias_n = normalize_text(alias)
        if alias_n and alias_n in text:
            return alias
    if not text:
        return None
    return description.strip()[:120]


def confidence_label(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"


def describe_category(category: str) -> str:
    return _CATEGORY_LABELS.get(category, "charge")
