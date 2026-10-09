"""Deterministic text-layer parser tests.

These cover the failure modes that actually showed up with real bill
documents: identifiers and dates that look like prices, a serial-number
column, and header rows packed with several ``Label: value`` pairs.
"""

from __future__ import annotations

import pytest

from app.providers.deterministic_parser import (
    _mask_identifiers,
    parse_bill_text,
    parse_fields,
)
from app.services.sample_documents import bill_lines


class TestIdentifierMasking:
    def test_dates_and_prefixed_ids_are_blanked_not_dropped(self):
        line = "Bill No:          DEMO-A-2026-0142                  Bill Date:  2026-02-18"
        masked = _mask_identifiers(line)
        assert len(masked) == len(line), "column positions must be preserved"
        assert "DEMO-A-2026-0142" not in masked
        assert "2026-02-18" not in masked
        assert masked.startswith("Bill No:")

    def test_real_prices_are_not_masked(self):
        line = "1    Private Room Charges                      5     4,700.00      23,500.00"
        assert _mask_identifiers(line) == line

    def test_negative_prices_are_not_masked(self):
        line = "11   Corporate Wellness Discount               1   -12,000.00     -12,000.00"
        assert _mask_identifiers(line) == line

    def test_percentages_are_masked(self):
        line = "12   GST @ 5%                                  1         0.00           0.00"
        assert "5%" not in _mask_identifiers(line)


class TestFieldParsing:
    def test_multiple_labels_on_one_line_are_all_extracted(self):
        fields = parse_fields(
            "Bill No:          DEMO-A-2026-0142                  Bill Date:  2026-02-18"
        )
        assert fields["bill_number"] == "DEMO-A-2026-0142"
        assert str(fields["bill_date"]) == "2026-02-18"

    def test_hospital_type_is_not_mistaken_for_the_hospital_name(self):
        fields = parse_fields(
            "City:             Kolkata    Hospital Type: multispecialty    "
            "Treatment: Internal Medicine"
        )
        assert fields["city"] == "Kolkata"
        assert "hospital_name" not in fields

    def test_length_of_stay_is_a_number_not_a_string(self):
        fields = parse_fields(
            "Room Category:    private                           Length of Stay:5 Days"
        )
        assert fields["room_category"] == "private"
        assert fields["length_of_stay_days"] == 5


class TestSampleBills:
    def test_every_bundled_sample_parses_into_charges(self):
        for key in ("A", "B", "C"):
            parsed = parse_bill_text("\n".join(bill_lines(key)))
            assert len(parsed.items) >= 9, f"scenario {key} lost its line items"
            assert not parsed.warnings, f"scenario {key}: {parsed.warnings}"

    def test_serial_column_is_not_read_as_a_quantity(self):
        parsed = parse_bill_text("\n".join(bill_lines("A")))
        by_name = {item.description: item for item in parsed.items}
        room = by_name["Private Room Charges"]
        # "1  Private Room Charges  5  4,700.00  23,500.00"
        assert (room.quantity, room.unit_price, room.total_price) == (5.0, 4700.0, 23500.0)

    def test_header_rows_are_not_charges(self):
        parsed = parse_bill_text("\n".join(bill_lines("A")))
        for item in parsed.items:
            assert "Bill No" not in item.description
            assert "Patient Name" not in item.description
            assert "Room Category" not in item.description

    def test_totals_and_metadata_come_through(self):
        parsed = parse_bill_text("\n".join(bill_lines("A")))
        assert parsed.fields["hospital_name"] == "Sunrise Multispecialty Hospital (Demo)"
        assert parsed.fields["city"] == "Kolkata"
        assert parsed.fields["room_category"] == "private"
        assert parsed.fields["stated_grand_total"] == 43950.0
        assert parsed.totals["subtotal"] == 55950.0
        # A discount printed as a positive magnitude becomes negative.
        assert parsed.totals["discount"] == -12000.0

    def test_zero_valued_tax_row_becomes_a_total_not_a_charge(self):
        parsed = parse_bill_text("\n".join(bill_lines("A")))
        assert parsed.totals.get("tax") == 0.0
        assert not any(item.description.startswith("GST") for item in parsed.items)

    def test_item_amounts_sum_to_the_stated_subtotal(self):
        for key in ("A", "B", "C"):
            parsed = parse_bill_text("\n".join(bill_lines(key)))
            positive = sum(i.total_price for i in parsed.items if i.total_price > 0)
            assert positive == parsed.totals["subtotal"], f"scenario {key} does not reconcile"


#: A statement laid out the way a real US hospital bill prints one: a mailing
#: address in the header, a date column, CPT/HCPCS codes, descriptions that wrap
#: onto a second line, and settlement rows under the total.
STATEMENT_TEXT = """\
MEDICAL BILLING
DEPARTMENT
P.O. Box 90210
Anytown, State 12345
Phone: 1-800-555-0199
STATEMENT OF
ACCOUNT
Account #: ACCT-93847291
Statement Date: 10/04/2026
PATIENT INFORMATION
Patient Name: John Doe
Date of Birth: 05/14/1982
Address: 123 Test Lane, Apt 4B
INSURANCE & GUARANTOR
Primary Insurance: Generic Health Plan Inc.
Date of
Service
Service
Code Description Qty Unit
Price
Total
Charge
09/25/2026 99284 Emergency Room Visit - Level 4 1 $850.00 $850.00
09/25/2026 70450 CT Scan Head/Brain w/o
Contrast 1 $1,200.00 $1,200.00
09/25/2026 85027 Complete Blood Count (CBC) 1 $45.00 $45.00
09/25/2026 80053 Comprehensive Metabolic Panel 1 $75.00 $75.00
09/25/2026 J7030 IV Saline Infusion 1000ml 2 $60.00 $120.00
09/25/2026 J2405 Pharmacy - Ondansetron
Injection 1 $65.00 $65.00
09/26/2026 REV0120 Room & Board - Semi-Private 1 $1,500.00 $1,500.00
09/26/2026 99232 Inpatient Physician Visit 1 $250.00 $250.00
Total Charges $4,105.00
Insurance Adjustment -$821.00
Insurance Paid -$2,463.00
Patient Payments $0.00
PATIENT BALANCE DUE $821.00
"""


@pytest.fixture(scope="module")
def parsed() -> "ParsedBill":
    return parse_bill_text(STATEMENT_TEXT)


class TestRealStatementLayout:
    def test_only_the_eight_charges_are_read(self, parsed):
        charges = [i for i in parsed.items if i.total_price > 0]
        assert len(charges) == 8
        assert [i.total_price for i in charges] == [
            850.0, 1200.0, 45.0, 75.0, 120.0, 65.0, 1500.0, 250.0,
        ]

    def test_charges_reconcile_with_the_printed_subtotal(self, parsed):
        charges = sum(i.total_price for i in parsed.items if i.total_price > 0)
        assert charges == parsed.totals["subtotal"] == 4105.0
        assert not parsed.warnings

    def test_the_insurance_write_off_is_not_a_charge(self, parsed):
        # It is printed below "Total Charges", so it belongs to the settlement
        # block rather than the charges table.
        assert [i.total_price for i in parsed.items] == [
            i.total_price for i in parsed.items if i.total_price > 0
        ]
        assert parsed.totals["insurance"] == -821.0

    def test_address_and_phone_numbers_are_not_charges(self, parsed):
        # The ZIP code 90210 and the phone number must never become prices.
        for description in (i.description for i in parsed.items):
            assert "P.O. Box" not in description
            assert "555" not in description
            assert not description.startswith("Anytown")

    def test_procedure_codes_are_not_read_as_amounts(self, parsed):
        amounts = {i.total_price for i in parsed.items}
        assert 70450.0 not in amounts, "CPT 70450 was read as a price"
        assert 99284.0 not in amounts, "CPT 99284 was read as a price"
        assert 90210.0 not in amounts, "the ZIP code was read as a price"

    def test_wrapped_descriptions_are_rejoined(self, parsed):
        descriptions = [i.description for i in parsed.items]
        assert "CT Scan Head/Brain w/o Contrast" in descriptions
        assert "Pharmacy - Ondansetron Injection" in descriptions
        assert "Contrast" not in descriptions, "a wrapped line became its own charge"

    def test_quantity_and_unit_price_survive(self, parsed):
        by_name = {i.description: i for i in parsed.items}
        saline = by_name["IV Saline Infusion 1000ml"]
        assert (saline.quantity, saline.unit_price, saline.total_price) == (2.0, 60.0, 120.0)

    def test_settlement_rows_are_totals_not_charges(self, parsed):
        descriptions = [i.description for i in parsed.items]
        assert not any("Insurance Paid" in d for d in descriptions)
        assert not any("Patient Payments" in d for d in descriptions)
        assert not any("BALANCE DUE" in d.upper() for d in descriptions)
        assert parsed.totals["insurance_paid"] == -2463.0
        assert parsed.totals["patient_payments"] == 0.0
        assert parsed.totals["patient_balance"] == 821.0

    def test_provider_and_patient_are_found(self, parsed):
        assert parsed.fields["hospital_name"] == "Medical Billing"
        assert parsed.fields["patient_name"] == "John Doe"


class TestWholeAmounts:
    def test_integer_amounts_inside_a_table_are_read(self):
        parsed = parse_bill_text(
            "SUNRISE HOSPITAL\n"
            "Sl.  Description                Qty      Rate      Amount\n"
            "1    Private Room Charges         4      4700      18800\n"
            "2    Consultant Doctor Fee        2      1200       2400\n"
            "Sub Total                                  21,200\n"
        )
        assert [i.description for i in parsed.items] == [
            "Private Room Charges",
            "Consultant Doctor Fee",
        ]
        assert [i.total_price for i in parsed.items] == [18800.0, 2400.0]

    def test_a_lone_integer_outside_a_table_is_not_a_charge(self):
        parsed = parse_bill_text(
            "CITY HOSPITAL\n"
            "P.O. Box 90210\n"
            "Anytown, State 12345\n"
            "Room Charges  2  1500.00  3000.00\n"
        )
        assert [i.total_price for i in parsed.items] == [3000.0]
