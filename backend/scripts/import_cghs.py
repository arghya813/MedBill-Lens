"""Build ``backend/data/cghs_benchmarks.json`` from the official CGHS rate list.

Source
------
Central Government Health Scheme (CGHS), Ministry of Health & Family Welfare,
Government of India — published rate list, served as structured JSON by
``https://www.cghs.mohfw.gov.in/AHIMSG5/hissso/Login?slug=rate-list``.

Every rate is expressed for a (tier, facility, ward) combination:

* tier      ``tier_i`` / ``tier_ii`` / ``tier_iii`` — city classification from
            O.M. No.2/5/2017-E.II(B) dated 07.07.2017 (X / Y / Z cities).
            Tier II is 10% below Tier I, Tier III 20% below (CGHS circular
            F.No.5-16/CGHS(HQ)/HEC/2024(PartI) dated 03.10.2025).
* facility  ``non_nabh`` / ``nabh`` / ``superspeciality``
* ward      ``general_ward`` / ``semi_private_ward`` / ``private_ward``

MedBill Lens stores one row per ``(city, hospital_category, service_name)``,
so the nine published cells of a service collapse into a band:

* ``min_price``     lowest of the nine cells
* ``median_price``  the NABH / semi-private cell (the O.M.'s base rate ``A``)
* ``max_price``     highest of the nine cells

City mapping (CGHS covered cities -> app cities)::

    Tier I  (X): Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune
    Tier II (Y): Jaipur

Usage
-----
    .\\.venv\\Scripts\\python.exe scripts\\import_cghs.py            # live fetch
    .\\.venv\\Scripts\\python.exe scripts\\import_cghs.py --offline  # cached copy
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:  # allow `python scripts/import_cghs.py`
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.enums import ChargeCategory, DatasetLabel  # noqa: E402

API_URL = "https://www.cghs.mohfw.gov.in/AHIMSG5/hislogin/getCghsRateListLgnFtr?inputCol={column}"
SOURCE_NAME = (
    "Central Government Health Scheme (CGHS), Ministry of Health & Family Welfare, "
    "Government of India — O.M. F.No.5-16/CGHS(HQ)/HEC/2024(PartI) dated 03.10.2025"
)
SOURCE_URL = "https://www.cghs.mohfw.gov.in/AHIMSG5/hissso/Login?slug=rate-list"
SOURCE_DATE = "2025-10-03"
DEFAULT_CACHE = BACKEND_DIR / "data" / "cghs_rates.json"
OUTPUT_PATH = BACKEND_DIR / "data" / "cghs_benchmarks.json"

TIERS = ("tier_i", "tier_ii", "tier_iii")
FACILITIES = ("non_nabh", "nabh", "superspeciality")
WARDS = ("general_ward", "semi_private_ward", "private_ward")
COLUMNS = tuple(f"{t}_{f}_{w}" for t in TIERS for f in FACILITIES for w in WARDS)
#: The nine cells that belong to one tier. ``str.startswith`` cannot be used
#: here: "tier_i" is a prefix of "tier_ii" and "tier_iii".
TIER_COLUMNS: dict[str, tuple[str, ...]] = {
    t: tuple(f"{t}_{f}_{w}" for f in FACILITIES for w in WARDS) for t in TIERS
}

#: App city -> CGHS city tier (verified against the CGHS covered-cities list and
#: the X/Y/Z classification of O.M. No.2/5/2017-E.II(B) dated 07.07.2017).
CITY_TIERS: dict[str, str] = {
    "Delhi": "tier_i",
    "Mumbai": "tier_i",
    "Bengaluru": "tier_i",
    "Hyderabad": "tier_i",
    "Chennai": "tier_i",
    "Kolkata": "tier_i",
    "Pune": "tier_i",
    "Jaipur": "tier_ii",
}
TIER_LABEL = {"tier_i": "Tier I", "tier_ii": "Tier II", "tier_iii": "Tier III"}
APP_TIER = {"tier_i": "tier1", "tier_ii": "tier2", "tier_iii": "tier3"}

#: CGHS code prefix -> MedBill Lens charge category.
PREFIX_CATEGORY: dict[str, str] = {
    "AG": ChargeCategory.SURGERY.value,  # Abdomen / GI surgery
    "BC": ChargeCategory.BLOOD_BANK.value,
    "BP": ChargeCategory.SURGERY.value,  # Burns & plastic surgery
    "BT": ChargeCategory.PROCEDURE.value,  # Behavioural therapy
    "BY": ChargeCategory.PROCEDURE.value,  # Biopsies
    "CA": ChargeCategory.LABORATORY.value,  # Oncology investigations (PCR etc.)
    "CC": ChargeCategory.ICU.value,
    "CI": ChargeCategory.IMAGING.value,  # ECG / TMT / Holter
    "CN": ChargeCategory.DOCTOR.value,
    "CP": ChargeCategory.SURGERY.value,  # Cardiology interventions
    "CT": ChargeCategory.PROCEDURE.value,  # Chemotherapy
    "CV": ChargeCategory.SURGERY.value,
    "DI": ChargeCategory.IMAGING.value,  # Dental radiographs (biopsy -> procedure)
    "DP": ChargeCategory.PROCEDURE.value,  # Dental procedures
    "EI": ChargeCategory.IMAGING.value,  # ENT investigations (audiometry)
    "EP": ChargeCategory.SURGERY.value,  # ENT procedures
    "GI": ChargeCategory.IMAGING.value,  # Gastro / nuclear-medicine studies
    "GP": ChargeCategory.PROCEDURE.value,
    "GS": ChargeCategory.PROCEDURE.value,  # Minor general surgery
    "HC": ChargeCategory.PACKAGE.value,  # Annual health check-up
    "HN": ChargeCategory.SURGERY.value,
    "IM": ChargeCategory.CONSUMABLES.value,  # Implant / graft / needle add-ons
    "IT": ChargeCategory.PROCEDURE.value,  # Radio-isotope therapy
    "LB": ChargeCategory.LABORATORY.value,
    "MG": ChargeCategory.PROCEDURE.value,  # Endoscopy
    "NI": ChargeCategory.IMAGING.value,  # EEG / EMG
    "NM": ChargeCategory.IMAGING.value,
    "NS": ChargeCategory.SURGERY.value,
    "NU": ChargeCategory.SURGERY.value,
    "OG": ChargeCategory.SURGERY.value,
    "OI": ChargeCategory.IMAGING.value,  # Ophthalmology investigations
    "OP": ChargeCategory.SURGERY.value,
    "OR": ChargeCategory.SURGERY.value,
    "PI": ChargeCategory.IMAGING.value,  # PFT / V-Q scan
    "PP": ChargeCategory.PROCEDURE.value,
    "PS": ChargeCategory.SURGERY.value,
    "PT": ChargeCategory.PROCEDURE.value,  # Physiotherapy
    "RI": ChargeCategory.IMAGING.value,
    "RP": ChargeCategory.PROCEDURE.value,  # Interventional radiology
    "RT": ChargeCategory.PROCEDURE.value,  # Radiotherapy
    "SK": ChargeCategory.PROCEDURE.value,
    "TM": ChargeCategory.SURGERY.value,  # Cancer surgery
    "US": "",  # placeholder codes ("Unspecified Code") — skipped
    "WC": ChargeCategory.ROOM.value,
}

#: Speciality-level overrides applied before the prefix table.
SPECIALITY_RULES: tuple[tuple[str, str], ...] = (
    ("ward charges", ChargeCategory.ROOM.value),
    ("critical care", ChargeCategory.ICU.value),
    ("blood component", ChargeCategory.BLOOD_BANK.value),
    ("consultation", ChargeCategory.DOCTOR.value),
    ("annual health check", ChargeCategory.PACKAGE.value),
    ("physiotherapy", ChargeCategory.PROCEDURE.value),
    ("behavioural therap", ChargeCategory.PROCEDURE.value),
    ("chemotherapy", ChargeCategory.PROCEDURE.value),
    ("radiotherapy", ChargeCategory.PROCEDURE.value),
    ("radio-isotope therapy", ChargeCategory.PROCEDURE.value),
)

UNIT_BY_CATEGORY: dict[str, str] = {
    ChargeCategory.ROOM.value: "per_day",
    ChargeCategory.ICU.value: "per_day",
    ChargeCategory.NURSING.value: "per_day",
    ChargeCategory.OXYGEN.value: "per_day",
    ChargeCategory.EQUIPMENT.value: "per_day",
    ChargeCategory.PHARMACY.value: "per_day",
    ChargeCategory.DOCTOR.value: "per_visit",
    ChargeCategory.LABORATORY.value: "per_order",
    ChargeCategory.IMAGING.value: "per_study",
    ChargeCategory.SURGERY.value: "per_case",
    ChargeCategory.PROCEDURE.value: "per_case",
    ChargeCategory.PACKAGE.value: "per_case",
    ChargeCategory.CONSUMABLES.value: "per_unit",
    ChargeCategory.BLOOD_BANK.value: "per_unit",
    ChargeCategory.MISCELLANEOUS.value: "per_unit",
}

RATE_RE = re.compile(r"\d{1,9}(?:,\d{1,3})*(?:\.\d+)?")
WHITESPACE_RE = re.compile(r"\s+")
NAME_LIMIT = 255


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def fetch_rates(timeout: float = 30.0) -> dict[str, dict[str, str]]:
    """Return ``{column: {cghs_code: published rate text}}`` for all 27 columns."""
    rates: dict[str, dict[str, str]] = {}
    for column in COLUMNS:
        request = urllib.request.Request(
            API_URL.format(column=column),
            headers={"Accept": "application/json", "User-Agent": "MedBill-Lens/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rates[column] = {
            row["alphanumeric_code"]: str(row.get(column, "")).strip()
            for row in payload.get("rateListArray", [])
        }
        print(f"  fetched {column}: {len(rates[column])} rows")
    return rates


def load_cache(path: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["rates"]


def fetch_catalogue(timeout: float = 30.0) -> dict[str, dict[str, str]]:
    """Fetch code -> name / speciality metadata for every published procedure."""
    first = COLUMNS[0]
    request = urllib.request.Request(
        API_URL.format(column=first),
        headers={"Accept": "application/json", "User-Agent": "MedBill-Lens/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        row["alphanumeric_code"]: {
            "name": str(row.get("cghs_treatment_procedure_investigation_list", "")).strip(),
            "speciality": str(row.get("speciality_classification", "")).strip(),
            "s_no": str(row.get("s_no", "")).strip(),
        }
        for row in payload.get("rateListArray", [])
    }


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def parse_rate(value: object) -> float | None:
    """Parse a published rate cell, tolerating ``"1,95,000+GST"`` style text."""
    if value is None:
        return None
    match = RATE_RE.search(str(value).replace("\u00a0", " "))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:  # pragma: no cover - regex guarantees digits
        return None


def clean_name(raw: str) -> str:
    return WHITESPACE_RE.sub(" ", raw).strip()[:NAME_LIMIT]


def derive_category(code: str, speciality: str) -> str:
    lowered = speciality.lower()
    for needle, category in SPECIALITY_RULES:
        if needle in lowered:
            return category
    if "biops" in lowered and code[:2] in {"DI", "NS", "NU", "OI", "BY"}:
        return ChargeCategory.PROCEDURE.value
    return PREFIX_CATEGORY.get(code[:2], ChargeCategory.MISCELLANEOUS.value)


def band(cells: list[float | None], preferred: float | None) -> tuple[float, float, float]:
    """Collapse the nine published cells into ``(min, median, max)``."""
    values = [v for v in cells if v is not None]
    if not values:
        raise ValueError("no numeric rate")
    low = min(values)
    high = max(values)
    middle = preferred if preferred is not None else sorted(values)[len(values) // 2]
    middle = min(max(middle, low), high)
    return low, middle, high


# ---------------------------------------------------------------------------
# Dataset build
# ---------------------------------------------------------------------------


def build_records(
    index: dict[str, dict[str, str]], rates: dict[str, dict[str, str]]
) -> tuple[list[dict], dict]:
    """Build one benchmark record per (city, service)."""
    categories: dict[str, str] = {}
    names: dict[str, str] = {}
    used_names: set[str] = set()

    for code in sorted(index):
        category = derive_category(code, index[code]["speciality"])
        if not category:
            continue
        name = clean_name(index[code]["name"])
        if not name:
            continue
        if name in used_names:  # three published services share a name
            name = clean_name(f"{name} ({code})")
        used_names.add(name)
        categories[code] = category
        names[code] = name

    # The set of unpublished ("Unlisted") codes is identical across all 27
    # columns, so the skip decision is made once rather than per city.
    importable: list[str] = []
    skipped_codes: set[str] = set()
    for code in sorted(categories):
        cells = [parse_rate(rates[col].get(code)) for col in COLUMNS]
        if all(cell is None for cell in cells):
            skipped_codes.add(code)
        else:
            importable.append(code)

    records: list[dict] = []

    for city, tier in CITY_TIERS.items():
        app_tier = APP_TIER[tier]
        for code in importable:
            cells = [parse_rate(rates[col].get(code)) for col in TIER_COLUMNS[tier]]
            preferred = parse_rate(rates[f"{tier}_nabh_semi_private_ward"].get(code))
            low, median, high = band(cells, preferred)
            info = index[code]
            records.append(
                {
                    "city": city,
                    "city_tier": app_tier,
                    "hospital_category": "government",
                    "service_name": names[code],
                    "service_category": categories[code],
                    "room_category": None,
                    "treatment": None,
                    "unit": UNIT_BY_CATEGORY.get(categories[code], "per_unit"),
                    "min_price": low,
                    "median_price": median,
                    "max_price": high,
                    "record_count": 1,
                    "currency_code": "INR",
                    "source_name": SOURCE_NAME,
                    "source_url": SOURCE_URL,
                    "source_date": SOURCE_DATE,
                    "verification_status": "government_rate",
                    "dataset_label": DatasetLabel.OFFICIAL_TARIFF.value,
                    "notes": (
                        f"CGHS code {code}. {info['speciality']}. Band = ward and "
                        f"facility range for {TIER_LABEL[tier]}."
                    ),
                }
            )

    metadata = {
        "dataset_label": DatasetLabel.OFFICIAL_TARIFF.value,
        "is_demo_data": False,
        "notice": (
            "Official government tariff dataset. Rates published by the Central Government "
            "Health Scheme (Ministry of Health & Family Welfare, Government of India). "
            "They are reference rates for CGHS-empanelled providers, not a hospital's "
            "posted tariff."
        ),
        "generator": "scripts.import_cghs",
        "generated_for": "MedBill Lens benchmark comparisons",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_date": SOURCE_DATE,
        "record_count": len(records),
        "cities": sorted(CITY_TIERS),
        "city_tier_mapping": {city: APP_TIER[tier] for city, tier in CITY_TIERS.items()},
        "codes_published": len(index),
        "codes_imported": len(importable),
        "codes_skipped": len(index) - len(importable),
        "retrieved_on": date.today().isoformat(),
    }
    return records, metadata


def write_dataset(path: Path, records: list[dict], metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Compact: this file is generated, never hand-edited, and a generated
    # dataset should not cost a megabyte of indentation.
    path.write_text(
        json.dumps(
            {"metadata": metadata, "records": records}, separators=(",", ":"), ensure_ascii=False
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="read a cached API payload")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="cache path")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="dataset path")
    args = parser.parse_args()

    if args.offline:
        payload = json.loads(args.cache.read_text(encoding="utf-8"))
        rates, index = payload["rates"], payload["index"]
        print(f"loaded {len(index)} procedures x {len(rates)} columns from {args.cache}")
    else:
        print("fetching CGHS rate list ...")
        rates = fetch_rates()
        index = fetch_catalogue()
        print(f"catalogued {len(index)} procedures")

    records, metadata = build_records(index, rates)
    write_dataset(args.output, records, metadata)
    print(f"wrote {len(records)} records to {args.output}")
    print(f"  published codes: {metadata['codes_published']}")
    print(f"  imported codes:  {metadata['codes_imported']}")
    print(f"  skipped codes:   {metadata['codes_skipped']} (unlisted / placeholders)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
