"""Generate the demo benchmark dataset.

IMPORTANT
---------
Every number produced by this script is **synthetic placeholder data** created
for development and hackathon demonstration. It does **not** represent real
hospital prices, government rates, insurance rates or any published tariff.

The generated file is written to ``data/demo_benchmarks.json`` with
``verification_status = "demo"`` and
``dataset_label = "Demo Benchmark Dataset"`` on every record, so that the API
and the UI can label it honestly. Real benchmark data is expected to be
loaded through a verified import (each record must carry its own source).

Run with::

    python -m app.services.demo_dataset
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.core.enums import (
    CATEGORY_LABELS,
    DATASET_NOTICES,
    ChargeCategory,
    DatasetLabel,
    HospitalCategory,
    RoomCategory,
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# Synthetic geography / facility parameters
# ---------------------------------------------------------------------------

CITIES: list[tuple[str, str, float]] = [
    # (city, tier, synthetic cost multiplier applied to the base figures)
    ("Delhi", "tier1", 1.22),
    ("Mumbai", "tier1", 1.28),
    ("Bengaluru", "tier1", 1.15),
    ("Hyderabad", "tier2", 0.95),
    ("Chennai", "tier2", 0.93),
    ("Kolkata", "tier2", 0.88),
    ("Pune", "tier2", 1.02),
    ("Jaipur", "tier3", 0.78),
]

HOSPITAL_CATEGORIES: list[tuple[str, float, list[str]]] = [
    # (category, synthetic multiplier, service categories it publishes)
    (
        HospitalCategory.GOVERNMENT.value,
        0.42,
        [
            ChargeCategory.ROOM.value,
            ChargeCategory.ICU.value,
            ChargeCategory.NURSING.value,
            ChargeCategory.DOCTOR.value,
            ChargeCategory.LABORATORY.value,
            ChargeCategory.IMAGING.value,
            ChargeCategory.PHARMACY.value,
            ChargeCategory.PROCEDURE.value,
            ChargeCategory.CONSUMABLES.value,
            ChargeCategory.OXYGEN.value,
        ],
    ),
    (
        HospitalCategory.MULTISPECIALTY.value,
        1.00,
        [
            ChargeCategory.ROOM.value,
            ChargeCategory.ICU.value,
            ChargeCategory.NURSING.value,
            ChargeCategory.DOCTOR.value,
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
        ],
    ),
    (
        HospitalCategory.SPECIALTY.value,
        0.92,
        [
            ChargeCategory.ROOM.value,
            ChargeCategory.ICU.value,
            ChargeCategory.DOCTOR.value,
            ChargeCategory.LABORATORY.value,
            ChargeCategory.IMAGING.value,
            ChargeCategory.PHARMACY.value,
            ChargeCategory.SURGERY.value,
            ChargeCategory.PROCEDURE.value,
            ChargeCategory.EQUIPMENT.value,
        ],
    ),
    (
        HospitalCategory.CLINIC.value,
        0.48,
        [
            ChargeCategory.ROOM.value,
            ChargeCategory.DOCTOR.value,
            ChargeCategory.LABORATORY.value,
            ChargeCategory.IMAGING.value,
            ChargeCategory.PHARMACY.value,
            ChargeCategory.PROCEDURE.value,
            ChargeCategory.CONSUMABLES.value,
        ],
    ),
    (
        HospitalCategory.DIAGNOSTIC_CENTRE.value,
        0.55,
        [
            ChargeCategory.IMAGING.value,
            ChargeCategory.LABORATORY.value,
        ],
    ),
    (
        HospitalCategory.PRIVATE.value,
        1.10,
        [
            ChargeCategory.ROOM.value,
            ChargeCategory.ICU.value,
            ChargeCategory.NURSING.value,
            ChargeCategory.DOCTOR.value,
            ChargeCategory.LABORATORY.value,
            ChargeCategory.IMAGING.value,
            ChargeCategory.PHARMACY.value,
            ChargeCategory.PROCEDURE.value,
            ChargeCategory.SURGERY.value,
            ChargeCategory.CONSUMABLES.value,
            ChargeCategory.EQUIPMENT.value,
            ChargeCategory.OXYGEN.value,
            ChargeCategory.MISCELLANEOUS.value,
        ],
    ),
]

# ---------------------------------------------------------------------------
# Synthetic base service catalogue
# ---------------------------------------------------------------------------
# (service_name, service_category, room_category, unit, base_median)
# Base figures are round synthetic numbers chosen only to exercise the
# comparison logic. They are not prices observed anywhere.

BASE_SERVICES: list[tuple[str, str, str | None, str, int]] = [
    # --- accommodation -------------------------------------------------
    ("General Ward Bed", ChargeCategory.ROOM.value, RoomCategory.GENERAL.value, "per_day", 1400),
    ("Semi Private Room", ChargeCategory.ROOM.value, RoomCategory.SEMI_PRIVATE.value, "per_day", 3200),
    ("Private Room", ChargeCategory.ROOM.value, RoomCategory.PRIVATE.value, "per_day", 5200),
    ("Deluxe Room", ChargeCategory.ROOM.value, RoomCategory.DELUXE.value, "per_day", 7800),
    ("Deluxe Suite", ChargeCategory.ROOM.value, RoomCategory.SUITE.value, "per_day", 14000),
    ("Intensive Care Unit ICU", ChargeCategory.ICU.value, RoomCategory.ICU.value, "per_day", 12500),
    ("Neonatal ICU NICU", ChargeCategory.ICU.value, RoomCategory.NICU.value, "per_day", 16000),
    ("Paediatric ICU PICU", ChargeCategory.ICU.value, RoomCategory.PICU.value, "per_day", 18500),
    ("Coronary Care Unit CCU", ChargeCategory.ICU.value, RoomCategory.CCU.value, "per_day", 15000),
    ("Nursing Care Charges", ChargeCategory.NURSING.value, None, "per_day", 900),
    # --- professional fees ---------------------------------------------
    ("Consultant Doctor Fee", ChargeCategory.DOCTOR.value, None, "per_visit", 1100),
    ("Senior Consultant Doctor Fee", ChargeCategory.DOCTOR.value, None, "per_visit", 1900),
    ("Surgeon Fee", ChargeCategory.DOCTOR.value, None, "per_case", 26000),
    ("Anaesthetist Fee", ChargeCategory.DOCTOR.value, None, "per_case", 7400),
    # --- diagnostics ---------------------------------------------------
    ("Laboratory Investigations", ChargeCategory.LABORATORY.value, None, "per_order", 2400),
    ("Routine Laboratory Test Panel", ChargeCategory.LABORATORY.value, None, "per_order", 1350),
    ("Advanced Laboratory Test Panel", ChargeCategory.LABORATORY.value, None, "per_order", 5200),
    ("X-Ray Imaging", ChargeCategory.IMAGING.value, None, "per_study", 850),
    ("Ultrasound Imaging", ChargeCategory.IMAGING.value, None, "per_study", 1600),
    ("CT Scan Imaging", ChargeCategory.IMAGING.value, None, "per_study", 4600),
    ("MRI Imaging", ChargeCategory.IMAGING.value, None, "per_study", 7800),
    ("Echocardiography", ChargeCategory.IMAGING.value, None, "per_study", 2300),
    # --- treatment ------------------------------------------------------
    ("Pharmacy Medicines and Medication", ChargeCategory.PHARMACY.value, None, "per_day", 2100),
    ("Procedure Charges", ChargeCategory.PROCEDURE.value, None, "per_case", 19500),
    ("Minor Procedure Charges", ChargeCategory.PROCEDURE.value, None, "per_case", 8600),
    ("Surgery Charges", ChargeCategory.SURGERY.value, None, "per_case", 44000),
    ("Minor Surgery Charges", ChargeCategory.SURGERY.value, None, "per_case", 21000),
    ("Consumables", ChargeCategory.CONSUMABLES.value, None, "per_case", 6300),
    ("Medical Consumables and Implants", ChargeCategory.CONSUMABLES.value, None, "per_unit", 1250),
    ("Equipment Usage and Monitoring", ChargeCategory.EQUIPMENT.value, None, "per_day", 1500),
    ("Ventilator Support", ChargeCategory.EQUIPMENT.value, None, "per_day", 3600),
    ("Oxygen and Medical Gas", ChargeCategory.OXYGEN.value, None, "per_day", 1150),
    ("Blood Bank Products", ChargeCategory.BLOOD_BANK.value, None, "per_unit", 2400),
    ("Miscellaneous Charges", ChargeCategory.MISCELLANEOUS.value, None, "per_visit", 700),
    # --- everyday bill phrasings -------------------------------------------
    # Real bills rarely say "Routine Laboratory Test Panel"; they say "CBC".
    # These rows mirror the wording hospitals actually print, so common
    # charges find a comparison instead of reporting no data. The figures
    # stay synthetic placeholders like every other row in this file.
    ("Complete Blood Count (CBC)", ChargeCategory.LABORATORY.value, None, "per_order", 350),
    ("Blood Sugar Test (Fasting/PP)", ChargeCategory.LABORATORY.value, None, "per_order", 150),
    ("HbA1c Test", ChargeCategory.LABORATORY.value, None, "per_order", 450),
    ("Lipid Profile", ChargeCategory.LABORATORY.value, None, "per_order", 900),
    ("Thyroid Profile (T3 T4 TSH)", ChargeCategory.LABORATORY.value, None, "per_order", 750),
    ("Liver Function Panel (LFT)", ChargeCategory.LABORATORY.value, None, "per_order", 800),
    ("Kidney Function Test (KFT)", ChargeCategory.LABORATORY.value, None, "per_order", 850),
    ("Urine Routine Test", ChargeCategory.LABORATORY.value, None, "per_order", 200),
    ("X-Ray Chest", ChargeCategory.IMAGING.value, None, "per_study", 350),
    ("Ultrasound Abdomen and Pelvis", ChargeCategory.IMAGING.value, None, "per_study", 1200),
    ("CT Scan Head/Brain", ChargeCategory.IMAGING.value, None, "per_study", 3500),
    ("MRI Brain", ChargeCategory.IMAGING.value, None, "per_study", 7000),
    ("ECG (Electrocardiogram)", ChargeCategory.IMAGING.value, None, "per_study", 250),
    ("Consultation Fee", ChargeCategory.DOCTOR.value, None, "per_visit", 600),
    ("Emergency Consultation Fee", ChargeCategory.DOCTOR.value, None, "per_visit", 1200),
    ("Follow-up Consultation Fee", ChargeCategory.DOCTOR.value, None, "per_visit", 400),
    ("Emergency Room Charges", ChargeCategory.ROOM.value, None, "per_day", 2000),
    ("Day Care Charges", ChargeCategory.ROOM.value, None, "per_day", 2500),
    ("Dressing Charges", ChargeCategory.PROCEDURE.value, None, "per_unit", 400),
    ("Injection and IV Charges", ChargeCategory.PROCEDURE.value, None, "per_unit", 300),
    ("IV Fluids (Infusion Charges)", ChargeCategory.PROCEDURE.value, None, "per_unit", 350),
    ("Nebulisation Charges", ChargeCategory.PROCEDURE.value, None, "per_unit", 350),
    ("Suturing and Suture Removal", ChargeCategory.PROCEDURE.value, None, "per_case", 800),
    ("Cataract Surgery with IOL", ChargeCategory.SURGERY.value, None, "per_case", 28000),
    ("Appendectomy (Appendix Removal)", ChargeCategory.SURGERY.value, None, "per_case", 65000),
    ("Hernia Repair Surgery", ChargeCategory.SURGERY.value, None, "per_case", 60000),
    ("Gallbladder Removal (Cholecystectomy)", ChargeCategory.SURGERY.value, None, "per_case", 70000),
    ("Registration and Admission Charges", ChargeCategory.MISCELLANEOUS.value, None, "per_visit", 300),
]

DEMO_SOURCE_NAME = "MedBill Lens synthetic demo dataset (not a published tariff)"
DEMO_SOURCE_DATE = date(2026, 1, 15)


def _round_to(value: float, step: int = 50) -> float:
    return float(int(round(value / step)) * step)


def build_records() -> list[dict]:
    records: list[dict] = []
    for city, tier, city_multiplier in CITIES:
        for category, category_multiplier, allowed in HOSPITAL_CATEGORIES:
            for service_name, service_category, room_category, unit, base_median in BASE_SERVICES:
                if service_category not in allowed:
                    continue
                # Government and clinic facilities publish fewer ICU/critical
                # services; skipping them keeps the demo set internally coherent.
                if room_category in {
                    RoomCategory.NICU.value,
                    RoomCategory.PICU.value,
                    RoomCategory.CCU.value,
                } and category not in {
                    HospitalCategory.MULTISPECIALTY.value,
                    HospitalCategory.PRIVATE.value,
                    HospitalCategory.SPECIALTY.value,
                }:
                    continue
                if room_category == RoomCategory.SUITE.value and category in {
                    HospitalCategory.CLINIC.value,
                    HospitalCategory.DIAGNOSTIC_CENTRE.value,
                }:
                    continue

                median = _round_to(
                    base_median * city_multiplier * category_multiplier,
                    step=100 if base_median >= 5000 else 50,
                )
                if median <= 0:
                    continue
                spread_low = 0.82 + 0.04 * ((len(city) + len(category)) % 4)
                spread_high = 1.16 + 0.05 * ((len(service_name) % 4))
                minimum = _round_to(median * spread_low, step=50)
                maximum = _round_to(median * spread_high, step=50)
                record_count = 3 + (len(service_name) * 7 + len(city) * 3) % 38

                records.append(
                    {
                        "city": city,
                        "city_tier": tier,
                        "hospital_category": category,
                        "service_name": service_name,
                        "service_category": service_category,
                        "room_category": room_category,
                        "treatment": None,
                        "unit": unit,
                        "min_price": minimum,
                        "median_price": median,
                        "max_price": maximum,
                        "record_count": record_count,
                        "currency_code": settings.currency_code,
                        "source_name": DEMO_SOURCE_NAME,
                        "source_url": "https://example.invalid/medbill-lens/demo-dataset",
                        "source_date": DEMO_SOURCE_DATE.isoformat(),
                        "verification_status": VerificationStatus.DEMO.value,
                        "dataset_label": DatasetLabel.DEMO_BENCHMARK.value,
                        "notes": (
                            "Synthetic placeholder value generated for development and "
                            "demonstration. Not a real price, tariff, or published rate."
                        ),
                    }
                )
    return records


def dataset_metadata() -> dict:
    return {
        "dataset_label": DatasetLabel.DEMO.value,
        "is_demo_data": True,
        "notice": DATASET_NOTICES[DatasetLabel.DEMO.value],
        "generator": "app.services.demo_dataset",
        "generated_for": "MedBill Lens development and hackathon demonstration",
        "record_count": len(build_records()),
        "categories_covered": sorted(
            {CATEGORY_LABELS.get(c, c) for c in {r["service_category"] for r in build_records()}}
        ),
    }


def write_dataset(path: Path | None = None) -> Path:
    target = path or (settings.data_path / "demo_benchmarks.json")
    payload = {
        "metadata": dataset_metadata(),
        "records": build_records(),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def load_dataset() -> list[dict]:
    """Load records from the JSON file, generating it first if absent."""
    path = settings.data_path / "demo_benchmarks.json"
    if not path.exists():
        write_dataset(path)
    return json.loads(path.read_text(encoding="utf-8")).get("records", [])


if __name__ == "__main__":  # pragma: no cover
    written = write_dataset()
    print(f"Wrote {len(build_records())} demo benchmark records to {written}")
    print("Reminder: these are synthetic placeholders, not real prices.")
