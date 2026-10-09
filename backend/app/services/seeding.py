"""Database seeding: benchmark datasets and demo sample bills."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.enums import (
    ADDITIVE_CATEGORIES,
    CREDIT_CATEGORIES,
    DATASET_NOTICES,
    BillStatus,
    ChargeCategory,
    DatasetLabel,
    RoomCategory,
)
from app.core.logging import get_logger
from app.models import Bill
from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.demo_dataset import dataset_metadata, load_dataset

logger = get_logger(__name__)


def dataset_paths() -> list[Path]:
    """Every bundled benchmark dataset, demo first, then official sources."""
    return sorted(settings.data_path.glob("*_benchmarks.json"))


def load_seed_records() -> list[dict]:
    """All bundled benchmark records (demo placeholders + published tariffs)."""
    # Generating the demo file first keeps a fresh checkout working even when
    # ``backend/data/`` is empty; the glob below then picks it up.
    load_dataset()
    records: list[dict] = []
    for path in dataset_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.extend(payload.get("records", []))
    # Files load demo-first, so a published tariff silently supersedes a
    # placeholder with the same (country, city, hospital type, service) key
    # instead of crashing the seed on the unique constraint.
    seen: dict[tuple[str, str, str, str], dict] = {}
    for record in records:
        record.setdefault("country_code", "IN")
        seen[
            (
                record["country_code"],
                record["city"],
                record["hospital_category"],
                record["service_name"],
            )
        ] = record
    return list(seen.values())


def seed_benchmarks(db: Session, *, force: bool = False, config: Settings | None = None) -> int:
    config = config or settings
    repo = BenchmarkRepository(db)
    if repo.count() > 0 and not force:
        return 0

    payload: list[dict] = []
    for record in load_seed_records():
        row = dict(record)
        if isinstance(row.get("source_date"), str):
            row["source_date"] = date.fromisoformat(row["source_date"])
        payload.append(row)

    if force:
        written = repo.upsert_many(payload)
    else:
        written = repo.insert_many(payload)
    db.commit()
    logger.info("benchmark_dataset_seeded records=%s", written)
    return written


def benchmark_metadata(db: Session) -> dict:
    """Dataset label / notice reflecting what is actually loaded."""
    repo = BenchmarkRepository(db)
    total = repo.count()
    verified = repo.count_verified()

    if verified == 0:
        label = DatasetLabel.DEMO.value
    elif verified == total:
        label = DatasetLabel.OFFICIAL_TARIFF.value
    else:
        label = DatasetLabel.MIXED.value

    meta = dataset_metadata()
    meta.update(
        {
            "dataset_label": label,
            "notice": DATASET_NOTICES[label],
            "is_demo_data": verified == 0,
            "record_count": total,
            "records_in_database": total,
            "verified_records": verified,
            "demo_records": total - verified,
            "datasets": [path.name for path in dataset_paths()],
        }
    )
    return meta


# ---------------------------------------------------------------------------
# Demo sample bills
# ---------------------------------------------------------------------------


def _bill(
    *,
    hospital_name: str,
    hospital_location: str,
    city: str,
    hospital_category: str,
    treatment: str,
    bill_number: str,
    bill_date: str,
    admission_date: str,
    discharge_date: str,
    room_type: str,
    items: list[dict],
    diagnosis: str = "",
    stated_grand_total: float | None = None,
) -> dict:
    """Build a scenario bill spec, deriving every total from the line items.

    Hard-coding ``subtotal``/``grand_total`` next to the items let the demo
    fixtures drift out of sync with their own line items, which produced
    nonsense totals in the UI. Everything is derived here instead.
    """
    charges = sum(
        float(item["total_price"])
        for item in items
        if item["category"] in ADDITIVE_CATEGORIES
    )
    credits = sum(
        abs(float(item["total_price"]))
        for item in items
        if item["category"] in CREDIT_CATEGORIES
    )
    taxes = sum(
        float(item["total_price"])
        for item in items
        if item["category"] == ChargeCategory.TAX.value
    )
    grand_total = charges - credits + taxes

    return {
        "hospital_name": hospital_name,
        "hospital_location": hospital_location,
        "city": city,
        "hospital_category": hospital_category,
        "treatment": treatment,
        "room_category": room_type,
        "bill_number": bill_number,
        "bill_date": bill_date,
        "admission_date": admission_date,
        "discharge_date": discharge_date,
        "diagnosis": diagnosis,
        "items": items,
        "subtotal": round(charges, 2),
        "grand_total": round(grand_total, 2),
        "stated_grand_total": (
            round(stated_grand_total, 2) if stated_grand_total is not None else round(grand_total, 2)
        ),
        "taxes_total": round(taxes, 2),
        "discounts_total": round(credits, 2),
        "insurance_deduction": 0.0,
    }


SCENARIOS: dict[str, dict] = {
    "A": {
        "key": "A",
        "title": "Scenario A — Charges mostly within benchmark",
        "description": (
            "A 5-day private-room stay where room, nursing, doctor and imaging charges "
            "sit inside the demo benchmark ranges."
        ),
        "expectation": (
            "Most charges should be reported as within the available benchmark range, "
            "with a small number that cannot be compared."
        ),
        "bill": _bill(
            hospital_name="Sunrise Multispecialty Hospital (demo)",
            hospital_location="Salt Lake Sector V, Kolkata, West Bengal",
            city="Kolkata",
            hospital_category="multispecialty",
            treatment="Internal Medicine",
            bill_number="DEMO-A-2026-0142",
            bill_date="2026-02-18",
            admission_date="2026-02-10",
            discharge_date="2026-02-15",
            room_type=RoomCategory.PRIVATE.value,
            diagnosis="Acute gastroenteritis",
            items=[
                {"description": "Private Room Charges", "category": ChargeCategory.ROOM.value,
                 "quantity": 5, "unit_price": 4700, "total_price": 23_500},
                {"description": "Nursing Care Charges", "category": ChargeCategory.NURSING.value,
                 "quantity": 5, "unit_price": 850, "total_price": 4250},
                {"description": "Consultant Doctor Fee", "category": ChargeCategory.DOCTOR.value,
                 "quantity": 3, "unit_price": 1250, "total_price": 3750},
                {"description": "Routine Laboratory Test Panel", "category": ChargeCategory.LABORATORY.value,
                 "quantity": 2, "unit_price": 1450, "total_price": 2900},
                {"description": "X-Ray Imaging", "category": ChargeCategory.IMAGING.value,
                 "quantity": 2, "unit_price": 900, "total_price": 1800},
                {"description": "Ultrasound Imaging", "category": ChargeCategory.IMAGING.value,
                 "quantity": 1, "unit_price": 1750, "total_price": 1750},
                {"description": "Pharmacy Medicines and Medication", "category": ChargeCategory.PHARMACY.value,
                 "quantity": 5, "unit_price": 2400, "total_price": 12_000},
                {"description": "Oxygen and Medical Gas", "category": ChargeCategory.OXYGEN.value,
                 "quantity": 3, "unit_price": 1250, "total_price": 3750},
                {"description": "Miscellaneous Charges", "category": ChargeCategory.MISCELLANEOUS.value,
                 "quantity": 1, "unit_price": 750, "total_price": 750},
                {"description": "Telemedicine Follow-up", "category": ChargeCategory.MISCELLANEOUS.value,
                 "quantity": 1, "unit_price": 1_500, "total_price": 1_500},
                {"description": "Corporate Wellness Discount", "category": ChargeCategory.DISCOUNT.value,
                 "quantity": 1, "unit_price": -12_000, "total_price": -12_000},
                {"description": "GST @ 5%", "category": ChargeCategory.TAX.value,
                 "quantity": 1, "unit_price": 0, "total_price": 0},
            ],
        ),
    },
    "B": {
        "key": "B",
        "title": "Scenario B — Several charges substantially above benchmark",
        "description": (
            "A surgical admission where the procedure, surgery, ICU and consumables "
            "charges sit well above the demo benchmark ranges, while the surgeon "
            "professional fee sits below its range."
        ),
        "expectation": (
            "Several charges should be flagged as 'Attention recommended' or "
            "'Review recommended', with an explanation and questions for each, and "
            "at least one charge should be reported as below range."
        ),
        "bill": _bill(
            hospital_name="Lakeshore Care Hospital (demo)",
            hospital_location="Alipore, Kolkata, West Bengal",
            city="Kolkata",
            hospital_category="multispecialty",
            treatment="General Surgery",
            bill_number="DEMO-B-2026-0087",
            bill_date="2026-03-04",
            admission_date="2026-02-26",
            discharge_date="2026-03-03",
            room_type=RoomCategory.ICU.value,
            diagnosis="Acute appendicitis with perforation",
            items=[
                {"description": "Private Room Charges", "category": ChargeCategory.ROOM.value,
                 "quantity": 3, "unit_price": 6000, "total_price": 18_000},
                {"description": "Intensive Care Unit ICU Charges", "category": ChargeCategory.ICU.value,
                 "quantity": 2, "unit_price": 17_500, "total_price": 35_000},
                {"description": "Nursing Care Charges", "category": ChargeCategory.NURSING.value,
                 "quantity": 5, "unit_price": 950, "total_price": 4750},
                {"description": "Surgeon Fee", "category": ChargeCategory.DOCTOR.value,
                 "quantity": 1, "unit_price": 9_500, "total_price": 9_500},
                {"description": "Laboratory Investigations", "category": ChargeCategory.LABORATORY.value,
                 "quantity": 3, "unit_price": 2_450, "total_price": 7_350},
                {"description": "CT Scan Imaging", "category": ChargeCategory.IMAGING.value,
                 "quantity": 1, "unit_price": 5_400, "total_price": 5_400},
                {"description": "Pharmacy Medicines and Medication", "category": ChargeCategory.PHARMACY.value,
                 "quantity": 5, "unit_price": 2_200, "total_price": 11_000},
                {"description": "Procedure Charges", "category": ChargeCategory.PROCEDURE.value,
                 "quantity": 1, "unit_price": 65_000, "total_price": 65_000},
                {"description": "Surgery Charges", "category": ChargeCategory.SURGERY.value,
                 "quantity": 1, "unit_price": 58_000, "total_price": 58_000},
                {"description": "Medical Consumables and Implants", "category": ChargeCategory.CONSUMABLES.value,
                 "quantity": 4, "unit_price": 1_450, "total_price": 5_800},
                {"description": "Ventilator Support", "category": ChargeCategory.EQUIPMENT.value,
                 "quantity": 2, "unit_price": 3_900, "total_price": 7_800},
                {"description": "Oxygen and Medical Gas", "category": ChargeCategory.OXYGEN.value,
                 "quantity": 2, "unit_price": 1_250, "total_price": 2_500},
            ],
        ),
    },
    "C": {
        "key": "C",
        "title": "Scenario C — Benchmark data unavailable for some charges",
        "description": (
            "A diagnostic-heavy bill in a smaller city, where several specialised "
            "services have no comparable benchmark record in the demo dataset."
        ),
        "expectation": (
            "The tool should say 'No sufficient benchmark data available' for those "
            "charges and must not invent an estimate."
        ),
        "bill": _bill(
            hospital_name="Neighbourhood Health Centre (demo)",
            hospital_location="Malviya Nagar, Jaipur, Rajasthan",
            city="Jaipur",
            hospital_category="specialty",
            treatment="Cardiology",
            bill_number="DEMO-C-2026-0311",
            bill_date="2026-01-27",
            admission_date="2026-01-24",
            discharge_date="2026-01-27",
            room_type=RoomCategory.SEMI_PRIVATE.value,
            diagnosis="Chest pain, evaluation",
            items=[
                {"description": "Semi Private Room Charges", "category": ChargeCategory.ROOM.value,
                 "quantity": 3, "unit_price": 2_450, "total_price": 7_350},
                {"description": "Consultant Doctor Fee", "category": ChargeCategory.DOCTOR.value,
                 "quantity": 2, "unit_price": 950, "total_price": 1_900},
                {"description": "Routine Laboratory Test Panel", "category": ChargeCategory.LABORATORY.value,
                 "quantity": 2, "unit_price": 1_250, "total_price": 2_500},
                {"description": "Echocardiography", "category": ChargeCategory.IMAGING.value,
                 "quantity": 1, "unit_price": 2_100, "total_price": 2_100},
                {"description": "ECG", "category": ChargeCategory.IMAGING.value,
                 "quantity": 2, "unit_price": 450, "total_price": 900},
                {"description": "Treadmill Stress Test", "category": ChargeCategory.IMAGING.value,
                 "quantity": 1, "unit_price": 4_200, "total_price": 4_200},
                {"description": "Coronary Angiography", "category": ChargeCategory.PROCEDURE.value,
                 "quantity": 1, "unit_price": 38_000, "total_price": 38_000},
                {"description": "Drug Eluting Stent Implant", "category": ChargeCategory.CONSUMABLES.value,
                 "quantity": 2, "unit_price": 16_500, "total_price": 33_000},
                {"description": "Cath Lab Charges", "category": ChargeCategory.PROCEDURE.value,
                 "quantity": 1, "unit_price": 6_450, "total_price": 6_450},
            ],
        ),
    },
}


def scenario_catalog() -> list[dict]:
    return [
        {
            "key": value["key"],
            "title": value["title"],
            "description": value["description"],
            "expectation": value["expectation"],
            "is_demo_data": True,
        }
        for value in SCENARIOS.values()
    ]


def _items_from_bill(bill: dict) -> list[dict]:
    return [
        {
            "description": item["description"],
            "category": item["category"],
            "service_name": item["description"],
            "quantity": float(item["quantity"]),
            "unit_price": float(item["unit_price"]),
            "total_price": float(item["total_price"]),
            "confidence": 1.0,
            "is_user_verified": True,
            "user_edited": True,
            "needs_confirmation": False,
            "source": "demo",
        }
        for item in bill["items"]
    ]


def create_scenario_bill(
    db: Session, scenario_key: str, *, config: Settings | None = None
) -> Bill:
    """Create a fully-confirmed demo bill ready for analysis. Idempotent."""
    config = config or settings
    scenario = SCENARIOS.get(scenario_key.upper())
    if scenario is None:
        raise KeyError(f"Unknown demo scenario '{scenario_key}'. Available: {', '.join(SCENARIOS)}")

    spec = scenario["bill"]
    existing = db.scalars(
        select(Bill).where(
            Bill.bill_number == spec["bill_number"],
        )
    ).first()
    if existing is not None:
        return existing

    from app.repositories.bill_repository import BillRepository
    from app.services.bill_service import BillService

    repo = BillRepository(db)
    bill = repo.create(
        status=BillStatus.CONFIRMED.value,
        source="demo",
        is_demo=True,
        hospital_name=spec["hospital_name"],
        hospital_location=spec["hospital_location"],
        city=spec["city"],
        hospital_category=spec["hospital_category"],
        treatment=spec["treatment"],
        room_category=spec["room_category"],
        patient_name="Demo Patient (sample data)",
        patient_id="DEMO-PID-0001",
        bill_number=spec["bill_number"],
        bill_date=date.fromisoformat(spec["bill_date"]),
        admission_date=date.fromisoformat(spec["admission_date"]),
        discharge_date=date.fromisoformat(spec["discharge_date"]),
        length_of_stay_days=(
            date.fromisoformat(spec["discharge_date"]) - date.fromisoformat(spec["admission_date"])
        ).days,
        diagnosis=spec["diagnosis"],
        stated_grand_total=spec.get("stated_grand_total"),
        currency_code=config.currency_code,
        extraction_meta={
            "provider": "demo",
            "method": "scenario_fixture",
            "is_real_provider": False,
            "dataset_label": DatasetLabel.DEMO.value,
            "scenario": scenario["key"],
        },
    )
    db.flush()

    repo.replace_items(bill, _items_from_bill(spec))
    service = BillService(db, config=config)
    service.recompute_totals(bill)
    repo.confirm(bill)
    db.commit()
    logger.info("demo_bill_created scenario=%s bill=%s", scenario["key"], bill.id)
    return bill
