"""Canonical vocabulary used across the backend, shared with the frontend."""

from __future__ import annotations

from enum import Enum


class ChargeCategory(str, Enum):
    DOCTOR = "doctor"
    ROOM = "room"
    ICU = "icu"
    NURSING = "nursing"
    LABORATORY = "laboratory"
    IMAGING = "imaging"
    PHARMACY = "pharmacy"
    PROCEDURE = "procedure"
    SURGERY = "surgery"
    CONSUMABLES = "consumables"
    EQUIPMENT = "equipment"
    OXYGEN = "oxygen"
    BLOOD_BANK = "blood_bank"
    PACKAGE = "package"
    MISCELLANEOUS = "miscellaneous"
    TAX = "tax"
    DISCOUNT = "discount"
    INSURANCE = "insurance"


#: Categories that represent an *addition* to the bill and are therefore
#: comparable against benchmarks. Tax / discount / insurance lines adjust the
#: payable total but are not themselves billable clinical services.
ADDITIVE_CATEGORIES: frozenset[str] = frozenset(
    {
        ChargeCategory.DOCTOR.value,
        ChargeCategory.ROOM.value,
        ChargeCategory.ICU.value,
        ChargeCategory.NURSING.value,
        ChargeCategory.LABORATORY.value,
        ChargeCategory.IMAGING.value,
        ChargeCategory.PHARMACY.value,
        ChargeCategory.PROCEDURE.value,
        ChargeCategory.SURGERY.value,
        ChargeCategory.CONSUMABLES.value,
        ChargeCategory.EQUIPMENT.value,
        ChargeCategory.OXYGEN.value,
        ChargeCategory.BLOOD_BANK.value,
        ChargeCategory.MISCELLANEOUS.value,
    }
)

#: Categories that reduce the payable amount.
CREDIT_CATEGORIES: frozenset[str] = frozenset(
    {ChargeCategory.DISCOUNT.value, ChargeCategory.INSURANCE.value}
)

#: Countries with bundled benchmark datasets. Codes are ISO 3166-1 alpha-2.
COUNTRY_LABELS: dict[str, str] = {
    "IN": "India",
    "AU": "Australia",
}

#: Categories that are purely regulatory/accounting entries.
NON_BENCHMARK_CATEGORIES: frozenset[str] = frozenset(
    {ChargeCategory.TAX.value}
) | CREDIT_CATEGORIES

CATEGORY_LABELS: dict[str, str] = {
    ChargeCategory.DOCTOR.value: "Doctor / Consultant",
    ChargeCategory.ROOM.value: "Room Charges",
    ChargeCategory.ICU.value: "ICU / Critical Care",
    ChargeCategory.NURSING.value: "Nursing",
    ChargeCategory.LABORATORY.value: "Laboratory",
    ChargeCategory.IMAGING.value: "Imaging & Diagnostics",
    ChargeCategory.PHARMACY.value: "Pharmacy / Medicines",
    ChargeCategory.PROCEDURE.value: "Procedures",
    ChargeCategory.SURGERY.value: "Surgery",
    ChargeCategory.CONSUMABLES.value: "Consumables",
    ChargeCategory.EQUIPMENT.value: "Equipment / Monitoring",
    ChargeCategory.OXYGEN.value: "Oxygen & Gas",
    ChargeCategory.BLOOD_BANK.value: "Blood Bank",
    ChargeCategory.PACKAGE.value: "Treatment Package",
    ChargeCategory.MISCELLANEOUS.value: "Miscellaneous",
    ChargeCategory.TAX.value: "Taxes",
    ChargeCategory.DISCOUNT.value: "Discounts",
    ChargeCategory.INSURANCE.value: "Insurance Deductions",
}


class HospitalCategory(str, Enum):
    GOVERNMENT = "government"
    PRIVATE = "private"
    MULTISPECIALTY = "multispecialty"
    SPECIALTY = "specialty"
    CLINIC = "clinic"
    DIAGNOSTIC_CENTRE = "diagnostic_centre"


class RoomCategory(str, Enum):
    GENERAL = "general"
    SEMI_PRIVATE = "semi_private"
    PRIVATE = "private"
    DELUXE = "deluxe"
    SUITE = "suite"
    ICU = "icu"
    NICU = "nicu"
    PICU = "picu"
    CCU = "ccu"
    EMERGENCY = "emergency"
    DAY_CARE = "day_care"


class FlagStatus(str, Enum):
    WITHIN_RANGE = "within_range"
    BELOW_RANGE = "below_range"
    REVIEW = "review"
    ATTENTION = "attention"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_COMPARABLE = "not_comparable"


FLAG_LABELS: dict[str, str] = {
    FlagStatus.WITHIN_RANGE.value: "Within benchmark range",
    FlagStatus.BELOW_RANGE.value: "Below benchmark range",
    FlagStatus.REVIEW.value: "Review recommended",
    FlagStatus.ATTENTION.value: "Attention recommended",
    FlagStatus.INSUFFICIENT_DATA.value: "No sufficient benchmark data",
    FlagStatus.NOT_COMPARABLE.value: "Not benchmarked",
}


class VerificationStatus(str, Enum):
    DEMO = "demo"
    UNVERIFIED = "unverified"
    PUBLISHED_TARIFF = "published_tariff"
    GOVERNMENT_RATE = "government_rate"
    OFFICIAL_DATASET = "official_dataset"
    VERIFIED_THIRD_PARTY = "verified_third_party"


#: Verification levels that may be presented as real-world reference data.
TRUSTED_VERIFICATION: frozenset[str] = frozenset(
    {
        VerificationStatus.PUBLISHED_TARIFF.value,
        VerificationStatus.GOVERNMENT_RATE.value,
        VerificationStatus.OFFICIAL_DATASET.value,
        VerificationStatus.VERIFIED_THIRD_PARTY.value,
    }
)


class DatasetLabel(str, Enum):
    DEMO = "Demo Dataset — Not for real-world financial decisions"
    DEMO_BENCHMARK = "Demo Benchmark Dataset"
    OFFICIAL_TARIFF = "Official Government Tariff Dataset"
    MIXED = "Mixed Demo and Official Benchmark Datasets"


#: Notices attached to benchmark payloads, keyed by what the corpus contains.
DATASET_NOTICES: dict[str, str] = {
    DatasetLabel.DEMO.value: (
        "Demo Dataset — Not for real-world financial decisions. All values in this "
        "dataset are synthetic placeholders created for software development. They "
        "are not hospital prices, government rates, or insurance rates."
    ),
    DatasetLabel.OFFICIAL_TARIFF.value: (
        "Official government tariff dataset. Rates are published by the Central "
        "Government Health Scheme (Ministry of Health & Family Welfare, Government "
        "of India) and are reference rates for CGHS-empanelled providers, not a "
        "hospital's posted tariff."
    ),
    DatasetLabel.MIXED.value: (
        "Mixed benchmark dataset. Records with a trusted verification status are "
        "published government tariffs; the remainder are synthetic demo placeholders "
        "and are not real-world prices."
    ),
}


class BillStatus(str, Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


#: Phrases that must never appear in generated output. Enforced as a safety
#: net in `app.utils.text.guard_language` and covered by tests.
PROHIBITED_TERMS: frozenset[str] = frozenset(
    {
        "fraud",
        "fraudulent",
        "scam",
        "scamming",
        "cheating",
        "cheated",
        "illegal",
        "illegally",
        "unlawful",
        "unlawfully",
        "malpractice",
        "criminal",
        "theft",
        "stole",
        "overcharged illegally",
        "guilty",
    }
)

SAFE_DISCLAIMER = (
    "MedBill Lens provides benchmark-based estimates for informational purposes. "
    "A higher charge does not necessarily mean that a hospital has made an incorrect "
    "or unlawful charge. Prices may vary because of treatment complexity, doctor fees, "
    "equipment, location, hospital facilities, emergency care, consumables, packages, "
    "and other factors."
)

TOOL_NOTICE = (
    "MedBill Lens is a bill-understanding and benchmark-comparison tool. It is not a "
    "medical diagnosis system, legal service, insurance adjudicator, or fraud-detection "
    "authority."
)
