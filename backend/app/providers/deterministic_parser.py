"""Deterministic bill text parser.

A rule-based reader for the *text layer* of a hospital bill. It is used by the
demo provider (where it is the whole extraction engine) and by the real
provider as a cross-check. It performs no AI calls and produces the same
output for the same input every time, which is exactly what makes it usable
as a clearly labelled demo mode.

Supported line shapes::

    1  Room Charges (General Ward)        5    2,000.00    10,000.00
    ICU Charges - 2 Days                  2   12,000.00    24,000.00
    Pharmacy                              1               4,500.00
    Discount                              1              -2,000.00
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.utils.text import normalize_text

# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

#: A currency token. Parentheses are accounting notation for a negative amount,
#: so ``(500.00)`` has to keep its sign instead of reading as 500.00.
_NUM_TOKEN = re.compile(
    r"\(?-?\s*(?:₹|Rs\.?|INR)\s*-?[\d,]+(?:\.\d{1,2})?\)?"
    r"|-?\(?[\d,]+(?:\.\d{1,2})?\)?"
)

_TRAILING_NUMBERS = re.compile(
    r"(?P<numbers>(?:\(?-?[\d,]+(?:\.\d{1,2})?\)?\s*){1,4})\s*$"
)

#: Currency glyphs are erased before a row is split into description and
#: numbers. They sit between the amount columns, so leaving them in place hides
#: the trailing price run that the split depends on.
_CURRENCY_GLYPHS = re.compile(r"[$₹]")

#: A number that actually looks like money: comma-grouped thousands or exactly
#: two decimal places. Bare integers are deliberately *not* accepted, which is
#: what keeps a ZIP code (90210) or a procedure code (99284) from being read as
#: the price of a charge. A row that carries a currency glyph counts as money
#: even without decimals, so ``$850`` is still accepted.
_MONEY_TOKEN = re.compile(
    r"(?<!\d)\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"
    r"|(?<!\d)\d+\.\d{2}(?!\d)"
)

#: Procedure / revenue codes printed beside the description (99284, J7030,
#: REV0120). These are masked only on rows that already carry a real price, so
#: the digits can never be mistaken for the amount. At least three digits are
#: required after the letters so a product name such as "Vitamin B12" survives.
_BARE_CODE = re.compile(r"\b\d{5}\b|\b[A-Z]{1,4}\d{3,5}\b")

#: Column headings that must never be glued onto the end of a description when
#: a row wraps onto a second line.
_CONTINUATION_BLOCKLIST = frozenset(
    {
        "total", "totals", "charge", "charges", "price", "amount", "qty",
        "quantity", "date", "service", "code", "description", "balance",
        "subtotal", "net", "paid", "due",
    }
)

_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b"),
    re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b", re.I),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

FIELD_LABELS: dict[str, str] = {
    "hospital name": "hospital_name",
    "name of hospital": "hospital_name",
    "hospital": "hospital_name",
    "institution name": "hospital_name",
    "centre name": "hospital_name",
    "center name": "hospital_name",
    "hospital address": "hospital_location",
    "address": "hospital_location",
    "location": "hospital_location",
    "city": "city",
    "patient name": "patient_name",
    "name of patient": "patient_name",
    "patient": "patient_name",
    "patient id": "patient_id",
    "patient no": "patient_id",
    "uhid": "patient_id",
    "mrd no": "patient_id",
    "mrd": "patient_id",
    "ip no": "patient_id",
    "bill no": "bill_number",
    "bill number": "bill_number",
    "bill #": "bill_number",
    "invoice no": "bill_number",
    "invoice number": "bill_number",
    "bill date": "bill_date",
    "date of bill": "bill_date",
    "invoice date": "bill_date",
    "date": "bill_date",
    "admission date": "admission_date",
    "admit date": "admission_date",
    "date of admission": "admission_date",
    "doa": "admission_date",
    "discharge date": "discharge_date",
    "date of discharge": "discharge_date",
    "dod": "discharge_date",
    "room category": "room_category",
    "room type": "room_category",
    "class of accommodation": "room_category",
    "accommodation": "room_category",
    "ward": "room_category",
    "length of stay": "length_of_stay_days",
    "los": "length_of_stay_days",
    "days": "length_of_stay_days",
    "no of days": "length_of_stay_days",
    "diagnosis": "diagnosis",
    "provisional diagnosis": "diagnosis",
    "final diagnosis": "diagnosis",
    "treatment": "diagnosis",
    "procedure performed": "diagnosis",
    "total days": "length_of_stay_days",
}

TOTAL_LABELS: tuple[str, ...] = (
    "grand total", "net payable", "net amount payable", "final total",
    "total payable", "amount payable", "total amount", "payable amount",
)

SUBTOTAL_LABELS: tuple[str, ...] = ("sub total", "subtotal", "gross total", "total charges")
DISCOUNT_LABELS: tuple[str, ...] = ("discount", "total discount", "discounts", "rebate", "concession")
INSURANCE_LABELS: tuple[str, ...] = (
    "insurance deduction", "insurance claim", "tpa deduction", "claim amount",
    "insurance settlement", "third party", "tpa",
)
TAX_LABELS: tuple[str, ...] = ("tax", "gst", "cgst", "sgst", "igst", "total tax", "taxes")

_FIELD_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z #/.'()\- ]{1,40}?)\s*[:\-]\s*(.+?)\s*$")

#: Tokens that *look* numeric to the number scanner but are really identifiers
#: or dates ("DEMO-A-2026-0142", "DEMO-PID-0001", "18/02/2026"). They are blanked
#: out before line-item parsing so a bill header is never mistaken for a charge.
_ID_OR_DATE = re.compile(
    # 18/02/2026, 2026-02-18, 18 Feb 2026
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    r"|\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b"
    r"|\b\d{4}-\d{1,2}-\d{1,2}\b"
    # Prefixed identifiers such as DEMO-A-2026-0142 or DEMO-PID-0001. The
    # mandatory leading letters keep real prices (4,700.00 / -12,000.00)
    # out of this branch.
    r"|\b[A-Za-z][A-Za-z0-9]*(?:[-_/][A-Za-z0-9]+)*\d[A-Za-z0-9_-]*\b"
    # Tax rates ("GST @ 5%") are percentages, not prices.
    r"|\b\d{1,3}(?:\.\d{1,2})?\s*%"
)

_SECTION_HEADINGS = re.compile(
    r"^\s*(?:\d+[.)]\s*)?(detail|description|particulars|particular|service|item|charge|"
    r"sl\.?\s*no|sl\s*no|description\s*of\s*service|charges?)\b.{0,20}$",
    re.I,
)

#: A PDF text layer often prints the column headings one word per line, so a
#: heading row can be as short as "Price" or "Total". These are table furniture,
#: not charges, and must never be mistaken for the totals block below the table.
_COLUMN_WORD = re.compile(
    r"^(?:date of service|service date|service code|code|description|particulars|"
    r"qty|quantity|unit price|price|rate|amount|total|charge|charges|balance|"
    r"sl\.?\s*no|s\.?\s*no|serial|item|comments?)\b[\s:.]*$",
    re.I,
)

#: Totals that close the charges table. A tax or discount row can sit in the
#: middle of a table, so only these end it.
_TERMINAL_TOTAL_KINDS = frozenset({"subtotal", "grand_total", "patient_balance"})

_HEADER_HINTS = re.compile(
    r"\b(sl\.?\s*no|description|particulars|qty|quantity|rate|amount|unit price|"
    r"particulars?\.?|description of service|charge details)\b",
    re.I,
)

_SKIP_LINE = re.compile(
    r"\b(page \d+|continued|signature|authorised signatory|generated on|"
    r"this is a computer generated|privileged & confidential|"
    r"thank you|get well soon|note:|terms)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ParsedItem:
    description: str
    quantity: float
    unit_price: float
    total_price: float
    confidence: float
    notes: str | None = None


@dataclass(slots=True)
class ParsedBill:
    fields: dict[str, object] = field(default_factory=dict)
    items: list[ParsedItem] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.5
    used_text_layer: bool = False


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def parse_number(token: str) -> float | None:
    """Parse a currency token, tolerating Indian digit grouping and negatives."""
    if token is None:
        return None
    text = token.strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if text.startswith("(") or text.endswith(")"):
        text = text.strip("()")
    text = re.sub(r"(₹|Rs\.?|rs\.?|INR)", "", text, flags=re.I)
    text = text.replace(",", "").replace(" ", "")
    if text in {"", "-", ".", "--"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return -abs(value) if negative else value


def extract_numbers(line: str) -> list[float]:
    """Return numeric tokens found in ``line``, in order."""
    out: list[float] = []
    for match in _NUM_TOKEN.finditer(line):
        # Skip the part before the first alphabetic character (label noise).
        start = match.start()
        value = parse_number(match.group())
        if value is not None:
            out.append(value)
        else:
            del start
    return out


def parse_date(text: str) -> date | None:
    for index, pattern in enumerate(_DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        try:
            if index == 0:
                day, month, year = (int(g) for g in match.groups())
                if year < 100:
                    year += 2000
                if year > 2100:
                    return None
                return date(year, month, day) if 1 <= month <= 12 else None
            if index == 1:
                day, month_name, year = match.group(1), match.group(2), int(match.group(3))
                month = _MONTHS.get(month_name.lower()[:3])
                return date(year, month, day) if month else None
            year, month, day = (int(g) for g in match.groups())
            return date(year, month, day)
        except (ValueError, TypeError):
            return None
    return None


def looks_like_date(token: str) -> bool:
    return any(p.search(token) for p in _DATE_PATTERNS)


def _clean_description(raw: str) -> str:
    text = re.sub(r"^\s*\d{1,3}\s*[.)\]]\s*", "", raw)  # leading serial number
    text = text.replace("\t", " ").strip()
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" .:;-|@\t")


def _has_money(text: str) -> bool:
    """True when the row carries something that can only be a price."""
    return bool(_CURRENCY_GLYPHS.search(text) or _MONEY_TOKEN.search(text))


def _strip_currency(line: str) -> str:
    """Erase currency glyphs so the trailing number run becomes contiguous."""
    stripped = _CURRENCY_GLYPHS.sub(" ", line)
    # ``-$821.00`` must stay a single negative token, not ``- 821.00``.
    return re.sub(r"-\s+(?=\d)", "-", stripped)


def _split_row(line: str, source: str | None = None) -> tuple[str, list[float]]:
    """Split a row into its description and its trailing number columns.

    Bills are printed as fixed-width tables, so the amount columns always sit at
    the end of the line. Splitting on the *trailing* run of numbers keeps the
    description intact, whereas scanning for the first price-like token used to
    cut a row short (``... Level 4 1 $850.00`` became ``... Level``).

    ``line`` is the identifier-masked copy used to read the numbers safely.
    ``source`` is the untouched copy of the same row: masking replaces a token
    with spaces of the same length, so the same offsets slice the description
    out of the original text and keep names like "Vitamin B12" intact.
    """
    match = _TRAILING_NUMBERS.search(line)
    if not match:
        return (source if source is not None else line), []
    head = line[: match.start()]
    if source is not None:
        head = source[: match.start()]
    return head, extract_numbers(match.group("numbers"))


#: A date that opens a charge row. It has to come off before the procedure code
#: is read, otherwise "09/25/2026 J7030 ..." yields the date as the code.
_LEADING_DATE = re.compile(
    r"^\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})\s+"
)


def _strip_leading_date(text: str) -> str:
    return _LEADING_DATE.sub("", text)


def _split_leading_code(description: str) -> tuple[str | None, str]:
    """Peel a leading procedure/revenue code off a description."""
    match = re.match(r"^\s*([A-Za-z]{0,4}\d{3,6})\s+(?=\S)", description)
    if not match:
        return None, description
    code = match.group(1)
    if not (code[:1].isdigit() or code[-1:].isdigit()):
        return None, description
    return code, description[match.end() :]


def _starts_new_row(stripped: str) -> bool:
    """True when a price-less line is the first half of a wrapped charge row.

    A date or a procedure code means the row has already begun, so the text is
    the head of the *next* charge rather than the tail of the current one.
    """
    return bool(_BARE_CODE.search(stripped)) or any(
        pattern.search(stripped) for pattern in _DATE_PATTERNS
    )


def _is_continuation(stripped: str) -> bool:
    """True when a price-less, code-less line continues the description above."""
    if not stripped or len(stripped) > 80:
        return False
    if _NUM_TOKEN.search(_strip_currency(stripped)):
        return False
    if normalize_text(stripped).strip(" .:-") in _CONTINUATION_BLOCKLIST:
        return False
    if _FIELD_LINE.match(stripped):
        return False
    return sum(ch.isalpha() for ch in stripped) >= 3


def _join_description(first: str, second: str) -> str:
    return re.sub(r"\s{2,}", " ", f"{first} {second}".strip())


def _mask_identifiers(line: str) -> str:
    """Blank out identifier/date tokens, preserving column positions.

    Bill headers are full of things like ``DEMO-A-2026-0142`` and
    ``DEMO-PID-0001``. Left alone, the number scanner treats the digits as
    prices and the header lines get parsed as charges. Replacing each match
    with spaces of the same length keeps the fixed-width column layout intact.
    """
    return _ID_OR_DATE.sub(lambda m: " " * len(m.group()), line)


def _is_probable_item_description(text: str) -> bool:
    if len(text) < 3 or len(text) > 220:
        return False
    letters = sum(ch.isalpha() for ch in text)
    if letters < 3:
        return False
    if re.fullmatch(r"[\d\s.,:/-]+", text):
        return False
    if _SKIP_LINE.search(text):
        return False
    return True


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------


#: Unanchored label marker, used to split a line that packs several
#: ``Label: value`` pairs into one fixed-width row
#: ("Bill No: X    Bill Date: 2026-02-18").
_FIELD_PAIR = re.compile(
    r"(?:^|(?<=\s\s)|(?<=:))\s*"
    r"(?P<label>[A-Za-z][A-Za-z #/.'()\-]{1,40}?)\s*[:\-]\s*"
    r"(?P<value>.*?)"
    r"(?=\s\s+[A-Za-z][A-Za-z #/.'()\-]{1,40}?\s*[:\-]\s*|$)"
)


#: Labels that must never be treated as a prefix of a longer label. Without
#: this, "Hospital Type: multispecialty" is read as the hospital's name.
_LABEL_BLOCKLIST: frozenset[str] = frozenset(
    {
        "hospital type",
        "hospital category",
        "hospital address",
        "type of hospital",
        "class of hospital",
    }
)


def _lookup_label(label: str) -> str | None:
    normalized = normalize_text(label)
    if not normalized or normalized in _LABEL_BLOCKLIST:
        return None
    key = FIELD_LABELS.get(normalized)
    if key:
        return key
    # Longest prefix wins, so "room category" is preferred over "room".
    candidates = sorted(
        (c for c in FIELD_LABELS if normalized.startswith(c)),
        key=len,
        reverse=True,
    )
    for candidate in candidates:
        remainder = normalized[len(candidate) :].strip()
        if remainder in _LABEL_BLOCKLIST:
            continue
        return FIELD_LABELS[candidate]
    return None


def parse_fields(text: str) -> dict[str, object]:
    fields: dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) > 200:
            continue
        if not _FIELD_LINE.match(line):
            continue
        # A single physical line can carry up to four label/value pairs, so it
        # is split before each known label is looked up.
        for match in _FIELD_PAIR.finditer(line):
            key = _lookup_label(match.group("label"))
            if not key:
                continue
            value = match.group("value").strip()
            if not value or normalize_text(value) in {"-", "--", "na", "n/a", "nil"}:
                continue

            if key == "city":
                fields.setdefault("city", value)
                continue
            if key.endswith("_date") or key == "bill_date":
                parsed = parse_date(value)
                if parsed and key not in fields:
                    fields[key] = parsed
                continue
            if key == "length_of_stay_days":
                parts = value.split()
                number = parse_number(parts[0]) if parts else None
                if number is not None and key not in fields:
                    fields[key] = int(number)
                continue
            if key not in fields:
                fields[key] = value

    if "admission_date" in fields and "discharge_date" in fields:
        try:
            delta = fields["discharge_date"] - fields["admission_date"]  # type: ignore[operator]
            if 0 <= delta.days <= 400:
                fields["length_of_stay_days"] = delta.days
        except Exception:
            pass
    if isinstance(fields.get("bill_date"), str):
        fields.pop("bill_date")
    return fields


def infer_hospital_name(text: str) -> str | None:
    """First non-empty, short, non-label line that looks like a hospital name."""
    for raw_line in text.splitlines()[:12]:
        line = raw_line.strip()
        if not line or len(line) > 90:
            continue
        if _FIELD_LINE.match(line):
            continue
        # Only genuine metadata labels are rejected. A provider printed as
        # "MEDICAL BILLING DEPARTMENT" is a name, not a bill field.
        if re.search(
            r"\b(bill|invoice)\s*(no|number|date|#|total|amount)\b\s*[:.]|"
            r"\b(patient|guarantor|account|policy|group)\b\s*[:.]",
            line,
            re.I,
        ):
            continue
        if any(ch.isdigit() for ch in line):
            continue
        if re.search(
            r"\b(hospital|medical|health|centre|center|institute|clinic|nursing home|"
            r"multispeciality|multispecialty|polyclinic|diagnostics?|hospitality|"
            r"medicines?|pharma|laborator(y|ies)|imaging|superspeciality)\b",
            line,
            re.I,
        ):
            return line.title() if line.isupper() else line
    return None


def infer_location(text: str) -> str | None:
    match = re.search(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*),\s*([A-Z][a-zA-Z\s]+?)(?:\s*-\s*\d{6})?\s*$", text, re.M)
    if match:
        return f"{match.group(1)}, {match.group(2).strip()}"
    match = re.search(r"\b(City\s*:\s*[^\n]+)", text, re.I)
    if match:
        return match.group(1).split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# Line-item parsing
# ---------------------------------------------------------------------------


def _is_table_header(stripped: str) -> bool:
    """True for the column-heading row that opens the charges table."""
    if _COLUMN_WORD.match(stripped):
        return True
    if _SECTION_HEADINGS.match(stripped):
        return True
    return bool(
        _HEADER_HINTS.search(stripped)
        and len(stripped) < 90
        and not _NUM_TOKEN.search(stripped)
    )


def _is_metadata_row(stripped: str) -> bool:
    """True for rows that carry bill metadata rather than a chargeable line."""
    if _is_table_header(stripped) or _SKIP_LINE.search(stripped):
        return True
    match = _FIELD_LINE.match(stripped)
    return bool(match and _lookup_label(match.group(1)))


def parse_line_items(text: str) -> tuple[list[ParsedItem], dict[str, float], list[str]]:
    """Read the charges table out of a bill's text layer.

    The table is bounded on both sides: parsing starts at the column-heading row
    and stops at the first totals row. Without those bounds a bill header is read
    as charges (a ZIP code becoming a $90,210 room charge) and the settlement
    rows below the total are read as further charges.
    """
    warnings: list[str] = []

    rows: list[tuple[int, str, str, str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        rows.append(
            (len(rows), stripped, _mask_identifiers(stripped), normalize_text(stripped))
        )

    # ---- pass 1: locate the charges table --------------------------------
    kinds: dict[int, str] = {}
    total_rows: set[int] = set()
    terminal_rows: set[int] = set()
    for index, stripped, _masked, lowered in rows:
        kind = _classify_total_line(lowered, stripped)
        if not kind:
            continue
        kinds[index] = kind
        total_rows.add(index)
        if kind in _TERMINAL_TOTAL_KINDS:
            terminal_rows.add(index)

    header_indexes = [index for index, s, _m, _l in rows if _is_table_header(s)]
    start = header_indexes[0] if header_indexes else 0
    later_totals = sorted(index for index in terminal_rows if index >= start)
    end = later_totals[0] if later_totals else len(rows)

    # ---- pass 2: totals and settlement rows ------------------------------
    # A bill often prints an adjustment twice: once inside the charges table
    # ("11  Corporate Wellness Discount  1  -12,000.00") and again in the
    # summary block ("Discounts  12,000.00"). The in-table row wins so the
    # figure is not counted twice.
    inside: dict[str, float] = {}
    outside: dict[str, float] = {}
    for index, _stripped, masked, _lowered in rows:
        kind = kinds.get(index)
        if not kind:
            continue
        amount = _last_amount(masked)
        if amount is None:
            continue
        if kind == "discount" and amount > 0:
            amount = -abs(amount)
        target = inside if index < end else outside
        target[kind] = round(target.get(kind, 0.0) + amount, 2)
    totals: dict[str, float] = {**outside, **inside}

    # ---- pass 3: the charges table itself --------------------------------
    items = _parse_charge_rows(rows, total_rows, terminal_rows, start, end)

    if not items:
        warnings.append(
            "No chargeable line items could be identified from the document text."
        )
    else:
        subtotal = totals.get("subtotal")
        if subtotal:
            # Bills print the subtotal either before or after their credit
            # lines, so both readings are accepted before warning.
            charges = round(
                sum(item.total_price for item in items if item.total_price > 0), 2
            )
            net = round(sum(item.total_price for item in items), 2)
            tolerance = max(1.0, abs(subtotal) * 0.005)
            if (
                abs(charges - subtotal) > tolerance
                and abs(net - subtotal) > tolerance
            ):
                warnings.append(
                    "The charges read from this document do not add up to the printed "
                    f"subtotal ({charges:,.2f} against {subtotal:,.2f}). Please review "
                    "the line items before continuing."
                )
    return items, totals, warnings


def _parse_charge_rows(
    rows: list[tuple[int, str, str, str]],
    total_rows: set[int],
    terminal_rows: set[int],
    start: int,
    end: int,
) -> list[ParsedItem]:
    items: list[ParsedItem] = []
    in_table = start > 0

    pending_item: ParsedItem | None = None
    pending_head: str | None = None
    pending_code: str | None = None

    for index, stripped, masked, _lowered in rows:
        if index < start:
            continue
        if index >= end:
            break

        # ---- metadata, headings and the totals block ----------------------
        if index in total_rows:
            if index in terminal_rows:
                break
            # An adjustment printed *inside* the table (a discount, a
            # contractual write-off) is a credit line the user should see and
            # reconcile, so it is parsed as a charge below. A zero-valued row
            # stays a total, and everything under the total stays a total.
            if not _row_amount(masked):
                pending_item, pending_head, pending_code = None, None, None
                continue
        if _is_metadata_row(stripped):
            pending_item, pending_head, pending_code = None, None, None
            continue

        # The row is split before it is judged. Bills that print whole amounts
        # ("4  4700  18800") are still charge rows, so once the charges table
        # has been located two or more amount columns are enough; outside it a
        # lone bare integer is an identifier (a ZIP code, a phone number).
        head, numbers = _split_row(_strip_currency(masked), _strip_currency(stripped))
        priced = _has_money(stripped) or (in_table and len(numbers) >= 2)

        if not priced:
            # No price: either the head of a wrapped row or its wrapped tail.
            if in_table and _starts_new_row(stripped):
                code, head_text = _split_leading_code(_strip_leading_date(stripped))
                head_text = _BARE_CODE.sub(" ", head_text)
                pending_head = _clean_description(_strip_currency(head_text)) or None
                pending_code = code
            elif pending_item is not None and _is_continuation(stripped):
                pending_item.description = _join_description(
                    pending_item.description, stripped
                )
            else:
                pending_item = None
            continue

        # ---- a priced row: description + amount columns -------------------
        numbers = _drop_serial_column(numbers)
        if not numbers:
            pending_item, pending_head, pending_code = None, None, None
            continue

        # Procedure codes are masked in the description only. Masking the whole
        # row would swallow a five digit total such as 18800.
        row_code = _split_leading_code(_strip_leading_date(stripped))[0]
        head = _strip_leading_date(head)
        head = _BARE_CODE.sub(lambda m: " " * len(m.group()), head)

        code, description = _split_leading_code(head)
        description = re.sub(r"^\s*\d{1,3}\s+", "", description)
        description = _clean_description(description)
        code = code or row_code
        if pending_head:
            description = _join_description(pending_head, description)
            code = code or pending_code
        pending_head, pending_code = None, None

        if not _is_probable_item_description(description):
            pending_item = None
            continue

        quantity, unit_price, total_price, confidence = _interpret_numbers(numbers)
        if total_price == 0.0 and numbers:
            total_price = numbers[-1]

        pending_item = ParsedItem(
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            total_price=round(total_price, 2),
            confidence=confidence,
            notes=f"Code {code}" if code else None,
        )
        items.append(pending_item)

    return items


#: Settlement rows printed under the total. They must never become charges, and
#: only the contractual adjustment feeds the insurance deduction. Matching is by
#: exact label so a charge such as "Payment Processing Fee" is not swallowed.
_SETTLEMENT_LABELS: tuple[tuple[frozenset[str], str], ...] = (
    (
        frozenset(
            {
                "insurance adjustment", "insurance adjustments", "contractual adjustment",
                "contractual adjustments", "insurance write off", "insurance writeoff",
                "adjustment", "adjustments", "write off", "writeoff",
            }
        ),
        "insurance",
    ),
    (
        frozenset(
            {
                "insurance paid", "paid by insurance", "paid by insurer", "plan paid",
                "payer paid", "insurer paid", "payment from insurer",
            }
        ),
        "insurance_paid",
    ),
    (
        frozenset(
            {
                "patient payment", "patient payments", "patient paid", "payments",
                "payment received",
            }
        ),
        "patient_payments",
    ),
    (
        frozenset(
            {
                "patient balance due", "patient balance", "patient responsibility",
                "balance due", "amount due", "you owe", "outstanding balance",
            }
        ),
        "patient_balance",
    ),
)


def _row_label(lowered: str) -> str:
    """Return the words that precede a row's first number.

    Bills print ``11   Corporate Wellness Discount   1   -12,000.00``, so the
    label is neither the whole line nor its suffix. Everything up to the first
    digit is the label; a serial number is dropped for free because it is one.
    """
    match = re.match(r"^\d{1,3}(?:\s+|$)", lowered)
    if match:
        lowered = lowered[match.end() :]
    head = re.match(r"^[^\d]*", lowered)
    label = head.group() if head else ""
    return re.sub(r"[$₹\s\-–:|.]+$", "", label).strip()


def _classify_total_line(lowered: str, raw: str) -> str | None:
    label = _row_label(lowered)

    # The label is tried first because it is the only part of a row that names
    # the figure; the whole line is kept as a fallback for layouts that print
    # the label after the amount.
    for candidate in (label, lowered):
        if not candidate:
            continue
        for names, kind in (
            (TOTAL_LABELS, "grand_total"),
            (SUBTOTAL_LABELS, "subtotal"),
            (TAX_LABELS, "tax"),
            (INSURANCE_LABELS, "insurance"),
            (DISCOUNT_LABELS, "discount"),
        ):
            if any(candidate.startswith(l) or candidate.endswith(l) for l in names):
                return kind

    for labels, kind in _SETTLEMENT_LABELS:
        if label in labels:
            return kind

    # A bare label such as "Total" only counts as a totals row when the amount
    # sits on the same line; on its own it is a column heading.
    if lowered in {"total", "total.", "amount", "amount payable:", "payable"} and _has_money(raw):
        return "grand_total"
    return None


def _row_amount(row: str) -> float:
    """Right-most amount on a row, or zero when it carries none."""
    amount = _last_amount(row)
    return amount if amount is not None else 0.0


def _last_amount(line: str) -> float | None:
    """Right-most amount on a row, keeping the sign in front of a currency glyph."""
    numbers = extract_numbers(_strip_currency(line))
    return numbers[-1] if numbers else None


def _drop_serial_column(numbers: list[float]) -> list[float]:
    """Remove a leading ``Sl. No.`` column if the remaining numbers add up.

    Item tables commonly print ``2  5  850.00  4,250.00``. The first number is
    a row counter, not a quantity, and it cannot be told apart from a quantity
    by value alone. The ``qty x rate == amount`` identity settles it, so the
    column is only dropped when the arithmetic actually works out.
    """
    if len(numbers) != 4:
        return numbers
    serial, quantity, rate, total = numbers
    if not (0 < serial <= 999 and serial == int(serial)):
        return numbers
    if not (0 < quantity <= 999 and quantity == int(quantity)):
        return numbers
    if abs(quantity * rate - total) <= max(1.0, abs(total) * 0.01):
        return numbers[1:]
    return numbers


def _interpret_numbers(numbers: list[float]) -> tuple[float, float, float, float]:
    """Work out (quantity, unit_price, total_price) from a row of numbers."""
    cleaned = [n for n in numbers if not looks_like_date(str(n))]
    if not cleaned:
        cleaned = numbers

    # A leading serial column was already resolved by ``_drop_serial_column``
    # using the ``qty * rate == amount`` identity. Nothing else may be dropped
    # here: a real quantity of 1 is far more common than a stray serial.
    cleaned = _drop_serial_column(cleaned)

    if len(cleaned) == 3:
        quantity, unit_price, total_price = cleaned
        return quantity, unit_price, total_price, 0.86
    if len(cleaned) == 2:
        first, second = cleaned
        if 0 < first <= 200 and first == int(first):
            # looks like quantity x amount, or unit price x amount
            if abs(first * second - second) < 1e-6:
                return 1.0, second, second, 0.7
            return first, second, second * first, 0.62
        return 1.0, first, second, 0.7
    total = cleaned[-1]
    return 1.0, total, total, 0.6


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_bill_text(text: str) -> ParsedBill:
    """Parse a bill's text layer into structured data. Fully deterministic."""
    if not text or not text.strip():
        return ParsedBill(warnings=["The document contained no readable text."], confidence=0.0)

    fields = parse_fields(text)
    items, totals, warnings = parse_line_items(text)

    if not fields.get("hospital_name"):
        name = infer_hospital_name(text)
        if name:
            fields["hospital_name"] = name
    if not fields.get("hospital_location"):
        location = infer_location(text)
        if location:
            fields["hospital_location"] = location

    # Prefer a stated grand total that the parser found.
    if "grand_total" in totals:
        fields["stated_grand_total"] = totals.pop("grand_total")

    # Merge any date-ish totals that belong in the structured fields.
    confidence = 0.5
    if items:
        confidence = min(0.95, 0.55 + 0.05 * min(len(items), 6))
    if fields.get("hospital_name"):
        confidence = min(0.95, confidence + 0.05)

    return ParsedBill(
        fields=fields,
        items=items,
        totals=totals,
        warnings=warnings,
        confidence=round(confidence, 2),
        used_text_layer=True,
    )


def merge_totals(parsed: ParsedBill, items_total: float) -> dict[str, float]:
    """Derive a consistent set of totals from parsed values and item sums."""
    totals = dict(parsed.totals)
    grand_total = parsed.fields.get("stated_grand_total")
    if not isinstance(grand_total, (int, float)) or grand_total == 0:
        subtotal = items_total
        net = (
            subtotal
            + (totals.get("tax") or 0.0)
            + (totals.get("discount") or 0.0)
            + (totals.get("insurance") or 0.0)
        )
        grand_total = round(net, 2)
    else:
        grand_total = round(float(grand_total), 2)

    return {
        "subtotal": round(float(totals.get("subtotal") or items_total), 2),
        "taxes_total": round(float(totals.get("tax") or 0.0), 2),
        "discounts_total": round(float(totals.get("discount") or 0.0), 2),
        "insurance_deduction": round(float(totals.get("insurance") or 0.0), 2),
        "grand_total": grand_total,
    }
