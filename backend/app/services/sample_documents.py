"""Generate the bundled sample bill documents.

Produces, for each demo scenario:

* ``<key>.txt`` - a plain-text bill (useful for reading and for tests)
* ``<key>.pdf`` - a minimal single-page PDF with the same text, so the upload
  flow can be exercised end to end without a real patient document.

These are synthetic fixtures. Every hospital name, number and patient detail is
fictional.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from app.core.config import settings
from app.services import seeding

_SCALE = 8  # character cell width/height scaling for the fixed-width font


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,.2f}"


def _wrap_header(hospital: str, location: str) -> list[str]:
    return [hospital.upper().center(78), location.center(78), "=" * 78]


def bill_lines(scenario_key: str) -> list[str]:
    spec = seeding.SCENARIOS[scenario_key.upper()]["bill"]
    lines: list[str] = []
    lines.extend(_wrap_header(spec["hospital_name"], spec["hospital_location"]))
    lines.append("")
    lines.append(f"{'Bill No:':<18}{spec['bill_number']:<34}{'Bill Date:':<12}{spec['bill_date']}")
    lines.append(f"{'Patient Name:':<18}{'Demo Patient (sample data)':<34}{'UHID:':<12}{'DEMO-PID-0001'}")
    lines.append(
        f"{'Admission Date:':<18}{spec['admission_date']:<34}{'Discharge Date:':<12}{spec['discharge_date']}"
    )
    stay = (
        __import__("datetime").date.fromisoformat(spec["discharge_date"])
        - __import__("datetime").date.fromisoformat(spec["admission_date"])
    ).days
    lines.append(f"{'Room Category:':<18}{spec['room_category']:<34}{'Length of Stay:':<12}{stay} Days")
    lines.append(f"{'Diagnosis:':<18}{spec['diagnosis']}")
    lines.append(f"{'City:':<18}{spec['city']}    Hospital Type: {spec['hospital_category']}    Treatment: {spec['treatment']}")
    lines.append("")
    lines.append("-" * 78)
    header = f"{'Sl.':<5}{'Description of Service':<36}{'Qty':>7}{'Rate':>13}{'Amount':>15}"
    lines.append(header)
    lines.append("-" * 78)

    for index, item in enumerate(spec["items"], start=1):
        description = item["description"]
        if len(description) > 34:
            description = description[:33] + "…"
        lines.append(
            f"{index:<5}{description:<36}{item['quantity']:>7}{_money(item['unit_price']):>13}"
            f"{_money(item['total_price']):>15}"
        )

    lines.append("-" * 78)
    lines.append(f"{'':<41}{'Sub Total':>15}{_money(spec['subtotal']):>15}")
    if spec.get("taxes_total"):
        lines.append(f"{'':<41}{'Taxes':>15}{_money(spec['taxes_total']):>15}")
    if spec.get("discounts_total"):
        lines.append(f"{'':<41}{'Discounts':>15}{_money(spec['discounts_total']):>15}")
    if spec.get("insurance_deduction"):
        lines.append(f"{'':<41}{'Insurance Deduction':>15}{_money(spec['insurance_deduction']):>15}")
    lines.append("-" * 78)
    lines.append(f"{'':<41}{'Grand Total':>15}{_money(spec['grand_total']):>15}")
    lines.append("-" * 78)
    lines.append("")
    lines.append("This is a computer generated document. All data shown is synthetic demo data.")
    return lines


# ---------------------------------------------------------------------------
# Minimal PDF writer (single page, Courier, no external dependency)
# ---------------------------------------------------------------------------


def _escape_pdf(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _text_lines(text: str, *, font_size: int = 8, leading: int = 10, max_chars: int = 108) -> list[list[str]]:
    raw = text.replace("\t", "    ").splitlines()
    wrapped: list[str] = []
    for line in raw:
        if len(line) <= max_chars:
            wrapped.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        remaining = line
        while len(remaining) > max_chars:
            cut = remaining.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            wrapped.append(remaining[:cut])
            remaining = " " * indent + remaining[cut:].lstrip()
        wrapped.append(remaining)
    pages: list[list[str]] = []
    lines_per_page = int(760 / leading)
    for start in range(0, len(wrapped), lines_per_page):
        pages.append(wrapped[start : start + lines_per_page])
    return pages or [[""]]


def build_pdf(lines: Sequence[str], *, title: str = "MedBill Lens sample bill") -> bytes:
    leading = 11
    pages = _text_lines("\n".join(lines))

    # Object ids are assigned explicitly so cross-references stay correct.
    font_id = 1
    n = len(pages)
    content_ids = list(range(2, 2 + n))
    page_ids = list(range(2 + n, 2 + 2 * n))
    pages_id = 2 + 2 * n
    catalog_id = pages_id + 1
    info_id = pages_id + 2

    objects: list[bytes] = [b""]  # 1-indexed

    def add(obj: bytes) -> None:
        objects.append(obj)

    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    for page in pages:
        stream_parts = ["BT", "/F1 8 Tf", f"{leading} TL", "1 0 0 1 40 800 Tm"]
        for line in page:
            stream_parts.append(f"({_escape_pdf(line)}) Tj T*")
        stream_parts.append("ET")
        stream = "\n".join(stream_parts).encode("latin-1", errors="replace")
        add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    for content_id in content_ids:
        add(
            b"<< /Type /Page /Parent "
            + str(pages_id).encode()
            + b" 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 "
            + str(font_id).encode()
            + b" 0 R >> >> /Contents "
            + str(content_id).encode()
            + b" 0 R >>"
        )

    kids = b" ".join(f"{pid} 0 R".encode() for pid in page_ids)
    add(
        b"<< /Type /Pages /Count "
        + str(n).encode()
        + b" /Kids ["
        + kids
        + b"] >>"
    )
    add(b"<< /Type /Catalog /Pages " + str(pages_id).encode() + b" 0 R >>")
    add(
        b"<< /Title ("
        + _escape_pdf(title).encode("latin-1", errors="replace")
        + b") /Producer (MedBill Lens) >>"
    )

    assert len(objects) - 1 == info_id, "pdf object numbering mismatch"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects[1:], start=1):
        offsets.append(len(out))
        out += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"

    xref_offset = len(out)
    count = len(objects)
    out += b"xref\n0 " + str(count).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(count).encode()
        + b" /Root "
        + str(catalog_id).encode()
        + b" 0 R /Info "
        + str(info_id).encode()
        + b" 0 R >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return bytes(out)


def write_samples(directory: Path | None = None) -> list[Path]:
    target = directory or settings.sample_bills_path
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key in seeding.SCENARIOS:
        lines = bill_lines(key)
        txt_path = target / f"scenario_{key.lower()}.txt"
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(txt_path)

        pdf_path = target / f"scenario_{key.lower()}.pdf"
        pdf_path.write_bytes(
            build_pdf(lines, title=f"MedBill Lens sample bill - Scenario {key}")
        )
        written.append(pdf_path)
    return written


if __name__ == "__main__":  # pragma: no cover
    for path in write_samples():
        print(f"wrote {path}")
