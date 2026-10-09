"""Build ``data/mbs_benchmarks.json`` from Australia's Medicare Benefits Schedule.

The MBS XML publishes every current item with its national schedule fee, so
unlike the CGHS import there is no per-city or per-ward structure: one fee
per item, applied identically in every listed city. ``min`` / ``median`` /
``max`` therefore collapse to the single scheduled fee, which the engine and
the UI already handle (a charge simply compares against one published number
instead of a band).

Usage
-----
    .\\.venv\\Scripts\\python.exe scripts\\import_mbs.py            # live fetch
    .\\.venv\\Scripts\\python.exe scripts\\import_mbs.py --offline  # cached copy
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:  # allow `python scripts/import_mbs.py`
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.enums import ChargeCategory, DatasetLabel  # noqa: E402

XML_URL = (
    "https://www.mbsonline.gov.au/internet/mbsonline/publishing.nsf/"
    "650f3eec0dfb990fca25692100069854/"
    "81efb2067580a870ca258e28007f588c7/$FILE/MBS-XML-20260801.XML"
)
SOURCE_NAME = (
    "Medicare Benefits Schedule (MBS), Australian Government Department of "
    "Health, Disability and Ageing"
)
SOURCE_URL = (
    "https://www.mbsonline.gov.au/internet/mbsonline/publishing.nsf/"
    "Content/Downloads-20260801"
)
SOURCE_DATE = "2026-08-01"  # schedule effective date of the imported XML

DEFAULT_CACHE = BACKEND_DIR / "data" / "mbs.xml"
OUTPUT_PATH = BACKEND_DIR / "data" / "mbs_benchmarks.json"

COUNTRY_CODE = "AU"
CITIES = ("Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide")
NAME_LIMIT = 255
WHITESPACE_RE = re.compile(r"\s+")

#: MBS category -> ChargeCategory. Category 3 is split: T8 holds the surgical
#: operations, every other therapeutic group is a procedure for our purposes.
CATEGORY_RULES: dict[str, str] = {
    "1": ChargeCategory.DOCTOR.value,
    "2": ChargeCategory.PROCEDURE.value,
    "4": ChargeCategory.PROCEDURE.value,
    "5": ChargeCategory.IMAGING.value,
    "6": ChargeCategory.LABORATORY.value,
    "7": ChargeCategory.PROCEDURE.value,
    "8": ChargeCategory.MISCELLANEOUS.value,
    "10": ChargeCategory.PROCEDURE.value,
}


def fetch_xml(timeout: float = 120.0) -> bytes:
    request = urllib.request.Request(
        XML_URL, headers={"Accept": "application/xml", "User-Agent": "MedBill-Lens/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _text(record: ET.Element, tag: str) -> str:
    element = record.find(tag)
    return (element.text or "").strip() if element is not None else ""


def clean_name(raw: str) -> str:
    return WHITESPACE_RE.sub(" ", raw).strip()[:NAME_LIMIT]


def derive_category(mbs_category: str, group: str) -> str:
    if mbs_category == "3":
        if group == "T8":
            return ChargeCategory.SURGERY.value
        return ChargeCategory.PROCEDURE.value
    return CATEGORY_RULES.get(mbs_category, ChargeCategory.MISCELLANEOUS.value)


def parse_items(payload: bytes) -> dict[str, dict]:
    """Current items with a numeric schedule fee, keyed by MBS item number."""
    root = ET.fromstring(payload)
    items: dict[str, dict] = {}
    skipped_ceased = 0
    skipped_derived = 0
    for record in root:
        if record.tag != "Data":
            continue
        if _text(record, "ItemEndDate"):
            skipped_ceased += 1
            continue
        try:
            fee = float(_text(record, "ScheduleFee"))
        except ValueError:
            skipped_derived += 1  # derived/relative-value fees carry no amount
            continue
        number = _text(record, "ItemNum")
        name = clean_name(_text(record, "Description"))
        if not number or not name:
            continue
        items[number] = {
            "name": name,
            "category": derive_category(_text(record, "Category"), _text(record, "Group")),
            "fee": fee,
            "group": _text(record, "Group"),
        }
    print(f"  parsed {len(items)} items "
          f"(skipped {skipped_ceased} ceased, {skipped_derived} derived-fee)")
    return items


def build_records(items: dict[str, dict]) -> tuple[list[dict], dict]:
    names: dict[str, str] = {}
    used_names: set[str] = set()
    for number in sorted(items, key=lambda n: (len(n), n)):
        name = items[number]["name"]
        if name in used_names:  # same head after truncation: keep both, labelled
            suffix = f"(MBS {number})"
            name = clean_name(f"{name[:NAME_LIMIT - len(suffix) - 1]} {suffix}")
        used_names.add(name)
        names[number] = name

    records: list[dict] = []
    for city in CITIES:
        for number in sorted(names):
            info = items[number]
            records.append(
                {
                    "country_code": COUNTRY_CODE,
                    "city": city,
                    "city_tier": "tier1",
                    "hospital_category": "government",
                    "service_name": names[number],
                    "service_category": info["category"],
                    "room_category": None,
                    "treatment": None,
                    "unit": "per_case"
                    if info["category"] == ChargeCategory.SURGERY.value
                    else "per_item",
                    "min_price": info["fee"],
                    "median_price": info["fee"],
                    "max_price": info["fee"],
                    "record_count": 1,
                    "currency_code": "AUD",
                    "source_name": SOURCE_NAME,
                    "source_url": SOURCE_URL,
                    "source_date": SOURCE_DATE,
                    "verification_status": "government_rate",
                    "dataset_label": DatasetLabel.OFFICIAL_TARIFF.value,
                    "notes": (
                        f"MBS item {number}. Australian national schedule fee, "
                        "same in all cities."
                    ),
                }
            )

    metadata = {
        "dataset_label": DatasetLabel.OFFICIAL_TARIFF.value,
        "is_demo_data": False,
        "notice": (
            "Official government tariff dataset. Schedule fees published in the "
            "Australian Medicare Benefits Schedule (Department of Health, "
            "Disability and Ageing). A single national fee per item, not a "
            "hospital's posted tariff."
        ),
        "generator": "scripts.import_mbs",
        "generated_for": "MedBill Lens benchmark comparisons",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_date": SOURCE_DATE,
        "record_count": len(records),
        "cities": sorted(CITIES),
        "items_published": len(items),
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
    parser.add_argument("--offline", action="store_true", help="read the cached XML")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="cache path")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="dataset path")
    args = parser.parse_args()

    if args.offline:
        payload = args.cache.read_bytes()
        print(f"loaded {len(payload)} bytes from {args.cache}")
    else:
        print("fetching MBS XML ...")
        payload = fetch_xml()
        args.cache.write_bytes(payload)
        print(f"fetched {len(payload)} bytes -> cached at {args.cache}")

    items = parse_items(payload)
    records, metadata = build_records(items)
    write_dataset(args.output, records, metadata)
    print(f"wrote {len(records)} records to {args.output}")
    print(f"  items published: {metadata['items_published']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
