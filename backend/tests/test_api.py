"""HTTP contract tests: upload -> review -> analyse -> report.

These run through the real FastAPI app with the deterministic demo provider, so
they cover routing, validation, error envelopes and the privacy behaviour a
client depends on.
"""

from __future__ import annotations

import io

import pytest

from app.core.enums import BillStatus
from app.services.sample_documents import build_pdf

SAMPLE_TEXT = """SUNRISE MULTISPECIALTY HOSPITAL
Kolkata, West Bengal

Bill No: TEST-0001              Bill Date: 2026-04-02
Patient Name: Test Patient      UHID: TEST-PID-1
Room Category: private          City: Kolkata

Sl.  Description                      Qty      Rate      Amount
1    Private Room Charges               4      4700      18800
2    Consultant Doctor Fee              2      1200       2400
3    Routine Laboratory Test Panel      2      1300       2600
4    X-Ray Imaging                      1      1800       1800
"""

#: The upload endpoint only accepts PDF/JPG/PNG and content-sniffs the bytes,
#: so tests build a real PDF out of the sample text rather than posting a .txt.
SAMPLE_PDF = build_pdf(SAMPLE_TEXT.splitlines())


def _upload(client, *, filename="bill.pdf", content_type="application/pdf", body=None):
    payload = SAMPLE_PDF if body is None else body
    return client.post(
        "/api/bills/upload",
        files={"file": (filename, io.BytesIO(payload), content_type)},
    )


def _bill_id(response) -> str:
    """Dig the bill id out of an upload response.

    Upload and manual-entry endpoints wrap the bill in ``{"bill": {...}}``,
    which keeps room for warnings and the suggested next step.
    """
    body = response.json()
    assert "bill" in body, f"expected a bill envelope, got keys {sorted(body)}"
    return body["bill"]["id"]


class TestHealthAndMetadata:
    def test_health_reports_the_active_provider(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["ai_provider"] == "demo"
        assert body["ai_provider_is_real"] is False
        assert body["database"] == "connected"
        assert body["benchmark_records"] > 0

    def test_options_expose_enums_for_the_ui(self, client):
        body = client.get("/api/options").json()
        for key in (
            "categories",
            "hospital_categories",
            "room_categories",
            "cities",
            "treatments",
            "demo_scenarios",
        ):
            assert body[key], f"{key} should not be empty"
        # Options drive the review screen's dropdowns, so they need stable
        # machine-readable values alongside their labels.
        assert {"value", "label"} <= set(body["categories"][0])

    def test_disclaimer_is_served(self, client):
        body = client.get("/api/disclaimer").json()
        assert "unlawful" in body["main"].lower()
        assert body["tool_notice"]
        assert body["privacy_notice"]
        assert body["dataset_notice"]

    def test_index_lists_endpoints(self, client):
        endpoints = client.get("/api").json()["endpoints"]; assert any("/api/health" in e for e in endpoints)


class TestBenchmarks:
    def test_stats_counts_are_not_inverted(self, client):
        body = client.get("/api/benchmarks/stats").json()
        assert body["total_records"] > 0
        assert body["demo_records"] + body["verified_records"] == body["total_records"]
        # Synthetic demo records ship alongside the published CGHS tariff.
        assert body["demo_records"] > 0
        assert body["verified_records"] > 0
        assert body["is_demo_data"] is False

    def test_records_carry_sources(self, client):
        body = client.get("/api/benchmarks", params={"limit": 5}).json()
        assert body["items"]
        for record in body["items"]:
            assert record["source_name"]
            assert record["dataset_label"]
            assert record["min_price"] <= record["median_price"] <= record["max_price"]

    def test_filters_apply(self, client):
        body = client.get(
            "/api/benchmarks", params={"city": "Kolkata", "limit": 10}
        ).json()
        assert body["items"]
        for record in body["items"]:
            assert record["city"] == "Kolkata"

    def test_verified_only_returns_published_tariffs(self, client):
        body = client.get("/api/benchmarks", params={"verified_only": True, "limit": 5}).json()
        assert body["items"]
        assert body["total"] > 0
        for record in body["items"]:
            assert record["verification_status"] != "demo"
            assert record["hospital_category"] == "government"
            assert record["currency_code"] == "INR"

    def test_government_tariffs_carry_full_provenance(self, client):
        body = client.get(
            "/api/benchmarks",
            params={
                "city": "Kolkata",
                "hospital_category": "government",
                "verified_only": True,
                "limit": 500,
            },
        ).json()
        assert body["total"] > 0
        assert body["is_demo_data"] is False
        for record in body["items"]:
            assert record["verification_status"] == "government_rate"
            assert "cghs.mohfw.gov.in" in record["source_url"]
            assert record["source_date"] is not None
            assert record["min_price"] <= record["median_price"] <= record["max_price"]
            assert "CGHS code" in record["notes"]

    def test_unknown_record_is_a_404_envelope(self, client):
        response = client.get("/api/benchmarks/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "benchmark_not_found"

    def test_private_bill_falls_back_to_same_city_tariffs(self, client):
        """A private-hospital bill compares against the city's published
        tariff when its own hospital type has no resembling record.

        Real bills say "Haemoglobin (Hb)", not "Routine Laboratory Test
        Panel": the demo rows for private hospitals do not resemble that
        wording, but the published CGHS tariff for the same city does, so the
        comparison must use it (labelled with its own source) instead of
        reporting no data.
        """
        created = client.post(
            "/api/bills",
            json={
                "items": [
                    {
                        "description": "Haemoglobin (Hb)",
                        "category": "laboratory",
                        "quantity": 1,
                        "unit_price": 60,
                        "total_price": 60,
                    },
                    {
                        "description": "Serum Creatinine",
                        "category": "laboratory",
                        "quantity": 1,
                        "unit_price": 130,
                        "total_price": 130,
                    },
                ],
                "context": {"city": "Kolkata", "hospital_category": "private"},
            },
        )
        assert created.status_code == 201
        analysis = client.post(
            f"/api/bills/{created.json()['bill']['id']}/analyze"
        ).json()["analysis"]
        fallback = [
            c
            for c in analysis["comparisons"]
            if c["match_scope"] == "hospital_category_relaxed"
        ]
        assert fallback
        for comparison in fallback:
            assert comparison["benchmark_available"] is True
            assert comparison["verification_status"] == "government_rate"
            assert comparison["benchmark_min"] <= comparison["benchmark_max"]


class TestUploadValidation:
    def test_rejects_unsupported_extension(self, client):
        response = _upload(
            client, filename="bill.exe", content_type="application/octet-stream"
        )
        assert response.status_code == 415
        body = response.json()
        assert body["error"]["code"] == "unsupported_file_type"
        assert "PDF" in body["error"]["message"]

    def test_rejects_oversized_file(self, client):
        response = _upload(client, body=b"a" * (11 * 1024 * 1024))
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "file_too_large"

    def test_rejects_empty_file(self, client):
        response = _upload(client, body=b"")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "corrupt_document"

    def test_rejects_a_file_that_only_claims_to_be_a_pdf(self, client):
        # Content sniffing, not just the extension: a renamed file must not
        # reach the PDF parser.
        response = _upload(
            client,
            filename="bill.pdf",
            content_type="application/pdf",
            body=b"this is not a pdf",
        )
        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_file_type"

    def test_missing_file_field_is_a_validation_error(self, client):
        response = client.post("/api/bills/upload")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


class TestBillLifecycle:
    def test_upload_creates_a_bill_awaiting_extraction(self, client):
        response = _upload(client)
        body = response.json()["bill"]
        # Upload only stores the document; extraction is a separate explicit
        # step so a user can choose manual entry instead.
        assert body["status"] == BillStatus.UPLOADED.value
        assert body["currency_code"] == "INR"
        assert body["items"] == []
        assert body["has_analysis"] is False
        assert response.json()["next_step"] == "extract"

    def test_extraction_reads_charges_and_asks_for_confirmation(self, client):
        bill_id = _bill_id(_upload(client))
        body = client.post(f"/api/bills/{bill_id}/extract").json()["bill"]
        assert body["status"] == BillStatus.AWAITING_CONFIRMATION.value
        assert body["items"], "extraction should find line items"
        # Unverified extraction output must be visibly provisional.
        assert all(item["is_user_verified"] is False for item in body["items"])
        descriptions = [i["description"] for i in body["items"]]
        assert any("Room" in d for d in descriptions)

    def test_extraction_reports_which_provider_was_used(self, client):
        bill_id = _bill_id(_upload(client))
        response = client.post(f"/api/bills/{bill_id}/extract").json()
        extraction = response["bill"]["extraction"]
        assert extraction["provider"] == "demo"
        # The UI must be able to label AI-assisted output honestly.
        assert extraction["is_real_provider"] is False
        assert extraction["method"] == "deterministic_rules"
        assert extraction["text_length"] > 0
        assert response["requires_confirmation"] is True

    def test_raw_documents_are_never_served(self, client):
        bill_id = _bill_id(_upload(client))
        client.post(f"/api/bills/{bill_id}/extract")
        for path in (
            f"/api/bills/{bill_id}/document",
            f"/api/bills/{bill_id}/raw",
            f"/api/bills/{bill_id}/file",
        ):
            assert client.get(path).status_code == 404

    def test_confirm_then_analyse_then_report(self, client):
        bill_id = _bill_id(_upload(client))
        extracted = client.post(f"/api/bills/{bill_id}/extract").json()["bill"]

        payload = {
            "items": [
                {
                    "description": item["description"],
                    "category": item["category"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                    "total_price": item["total_price"],
                }
                for item in extracted["items"]
            ],
            "metadata": {"hospital_name": "Sunrise Multispecialty Hospital"},
            # City/hospital type/treatment/room select the benchmark records
            # and belong in ``context``, not ``metadata``.
            "context": {
                "city": "Kolkata",
                "hospital_category": "multispecialty",
                "treatment": "Internal Medicine",
                "room_category": "private",
            },
        }
        confirmed = client.put(f"/api/bills/{bill_id}/items", json=payload)
        assert confirmed.status_code == 200
        # The review endpoint returns the bill directly; only upload/extract
        # wrap it in an envelope.
        assert confirmed.json()["status"] == BillStatus.CONFIRMED.value

        analysis = client.post(f"/api/bills/{bill_id}/analyze").json()["analysis"]
        assert analysis["comparisons"]
        assert analysis["totals"]["bill_total"] > 0
        assert analysis["disclaimer"]
        assert analysis["is_demo_data"] is True

        report = client.get(f"/api/bills/{bill_id}/report", params={"format": "json"})
        body = report.json()
        assert body["anonymized"] is True
        assert any(section["key"] == "sources" for section in body["sections"])

    def test_analysis_requires_confirmation_first(self, client):
        bill_id = _bill_id(_upload(client))
        response = client.post(f"/api/bills/{bill_id}/analyze")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "bill_not_confirmed"

    def test_get_analysis_before_running_is_a_409(self, client):
        bill_id = _bill_id(_upload(client))
        response = client.get(f"/api/bills/{bill_id}/analysis")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "analysis_not_ready"

    def test_manual_entry_works_without_upload(self, client):
        response = client.post(
            "/api/bills",
            json={
                "items": [
                    {
                        "description": "Consultant Doctor Fee",
                        "category": "doctor",
                        "quantity": 2,
                        "unit_price": 900,
                        "total_price": 1800,
                    }
                ],
                "metadata": {"hospital_name": "City Clinic"},
                "context": {"city": "Kolkata"},
            },
        )
        assert response.status_code == 201
        body = response.json()["bill"]
        assert body["status"] == BillStatus.CONFIRMED.value
        assert body["totals"]["grand_total"] == 1800
        assert response.json()["next_step"] == "analyze"

    def test_unknown_bill_is_a_404_envelope(self, client):
        response = client.get("/api/bills/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "bill_not_found"

    def test_delete_removes_the_bill(self, client):
        bill_id = _bill_id(_upload(client))
        assert client.delete(f"/api/bills/{bill_id}").status_code == 200
        assert client.get(f"/api/bills/{bill_id}").status_code == 404

    def test_negative_credit_lines_are_accepted(self, client):
        response = client.post(
            "/api/bills",
            json={
                "items": [
                    {
                        "description": "Room Charges",
                        "category": "room",
                        "quantity": 1,
                        "unit_price": 10000,
                        "total_price": 10000,
                    },
                    {
                        "description": "Corporate Discount",
                        "category": "discount",
                        "quantity": 1,
                        "unit_price": -2000,
                        "total_price": -2000,
                    },
                ],
            },
        )
        assert response.status_code == 201
        # Manual entry is confirmed on creation, so it can go straight to
        # analysis without the upload -> extract -> confirm round trip.
        assert response.json()["bill"]["totals"]["grand_total"] == 8000
        assert response.json()["next_step"] == "analyze"

    def test_unknown_keys_are_rejected_not_ignored(self, client):
        # A context field posted inside ``metadata`` used to be dropped
        # silently, which changed which benchmarks matched and produced
        # completely different numbers with a 200 response.
        response = client.post(
            "/api/bills",
            json={
                "items": [
                    {
                        "description": "Consultant Doctor Fee",
                        "category": "doctor",
                        "quantity": 1,
                        "unit_price": 900,
                        "total_price": 900,
                    }
                ],
                "metadata": {"hospital_category": "multispecialty"},
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def _preview_items(bill, **overrides):
    """The review screen's table, one entry per extracted row, keyed by id."""
    items = [
        {
            "key": item["id"],
            "id": item["id"],
            "description": item["description"],
            "category": item["category"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "total_price": item["total_price"],
        }
        for item in bill["items"]
    ]
    for index, patch in overrides.items():
        items[int(index)].update(patch)
    return items


#: What the review screen sends alongside the table.
PREVIEW_CONTEXT = {
    "city": "Kolkata",
    "hospital_category": "multispecialty",
    "treatment": "Internal Medicine",
    "room_category": "private",
}


class TestReviewPreview:
    """Live per-charge comparison on the review screen, before confirming."""

    def _extracted(self, client):
        bill_id = _bill_id(_upload(client))
        bill = client.post(f"/api/bills/{bill_id}/extract").json()["bill"]
        return bill_id, bill

    def test_preview_runs_before_the_bill_is_confirmed(self, client):
        bill_id, bill = self._extracted(client)
        assert bill["status"] == BillStatus.AWAITING_CONFIRMATION.value

        response = client.post(
            "/api/bills/preview",
            json={
                "bill_id": bill_id,
                "items": _preview_items(bill),
                "context": PREVIEW_CONTEXT,
            },
        )
        assert response.status_code == 200
        body = response.json()
        # The whole point: comparison without confirmation, where the full
        # analysis endpoint is still a 409.
        assert client.post(f"/api/bills/{bill_id}/analyze").status_code == 409
        assert len(body["comparisons"]) == len(bill["items"])
        assert body["headline"]
        assert body["disclaimer"]
        assert body["counts"]["analyzed"] == len(bill["items"])
        assert body["context"]["city"] == "Kolkata"

    def test_every_row_is_keyed_so_statuses_follow_the_right_charge(self, client):
        _, bill = self._extracted(client)
        response = client.post(
            "/api/bills/preview",
            json={"items": _preview_items(bill), "context": PREVIEW_CONTEXT},
        )
        body = response.json()
        for index, (row, item) in enumerate(
            zip(body["comparisons"], bill["items"], strict=True)
        ):
            assert row["id"] == item["id"], "the client's row key must come back"
            assert row["sort_index"] == index
            assert row["description"] == item["description"]
            assert row["actual_amount"] == item["total_price"]
            assert row["flag_status"] in {
                "within_range",
                "below_range",
                "review",
                "attention",
                "insufficient_data",
                "not_comparable",
            }

    def test_blank_rows_are_skipped_but_the_others_keep_their_keys(self, client):
        _, bill = self._extracted(client)
        items = [{"key": "row-blank", "description": "", "category": "other"}]
        items += _preview_items(bill)

        body = client.post("/api/bills/preview", json={"items": items}).json()
        ids = [row["id"] for row in body["comparisons"]]
        assert "row-blank" not in ids
        assert ids == [item["id"] for item in bill["items"]]
        # No blank description can reach the client as a fake charge.
        assert all(row["description"].strip() for row in body["comparisons"])

    def test_unsaved_edits_change_the_flags(self, client):
        bill_id, bill = self._extracted(client)
        room_index = next(
            i for i, item in enumerate(bill["items"]) if item["category"] == "room"
        )

        def flags(items):
            return {
                row["id"]: row["flag_status"]
                for row in client.post(
                    "/api/bills/preview",
                    json={"bill_id": bill_id, "items": items, "context": PREVIEW_CONTEXT},
                ).json()["comparisons"]
            }

        before = flags(_preview_items(bill))
        inflated = _preview_items(
            bill, **{str(room_index): {"quantity": 1, "unit_price": 999999, "total_price": 999999}}
        )
        after = flags(inflated)

        assert after[bill["items"][room_index]["id"]] in {"attention", "review"}
        assert before[bill["items"][room_index]["id"]] != after[
            bill["items"][room_index]["id"]
        ], "an edited charge must be re-evaluated before it is saved"

    def test_preview_writes_nothing(self, client):
        bill_id, bill = self._extracted(client)
        inflated = _preview_items(
            bill, **{"0": {"quantity": 1, "unit_price": 999999, "total_price": 999999}}
        )
        assert (
            client.post(
                "/api/bills/preview",
                json={"bill_id": bill_id, "items": inflated, "context": PREVIEW_CONTEXT},
            ).status_code
            == 200
        )

        stored = client.get(f"/api/bills/{bill_id}").json()
        assert stored["status"] == BillStatus.AWAITING_CONFIRMATION.value
        assert stored["has_analysis"] is False
        assert stored["items"][0]["total_price"] == bill["items"][0]["total_price"]

    def test_preview_works_without_a_bill_for_manual_entry(self, client):
        items = [
            {
                "key": "row-1",
                "description": "Consultant Doctor Fee",
                "category": "doctor",
                "quantity": 2,
                "unit_price": 900,
                "total_price": 1800,
            }
        ]
        body = client.post("/api/bills/preview", json={"items": items}).json()
        assert body["bill_id"] is None
        assert len(body["comparisons"]) == 1
        assert body["comparisons"][0]["id"] == "row-1"
        assert body["comparisons"][0]["actual_amount"] == 1800

    def test_preview_reports_which_dataset_was_used(self, client):
        items = [
            {
                "key": "row-1",
                "description": "Consultant Doctor Fee",
                "category": "doctor",
                "quantity": 1,
                "unit_price": 900,
                "total_price": 900,
            }
        ]
        body = client.post("/api/bills/preview", json={"items": items}).json()
        assert body["dataset_label"]
        assert body["is_demo_data"] is True
        assert any("demo" in notice.lower() for notice in body["notices"])

    def test_preview_rejects_an_unknown_bill_id(self, client):
        response = client.post(
            "/api/bills/preview",
            json={"bill_id": "nope", "items": [{"key": "a", "description": "Room"}]},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "bill_not_found"

    def test_preview_rejects_unknown_fields_not_ignored(self, client):
        response = client.post(
            "/api/bills/preview",
            json={"items": [{"key": "a", "description": "Room"}], "bogus": 1},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_preview_needs_at_least_one_row(self, client):
        response = client.post("/api/bills/preview", json={"items": []})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


class TestDemoEndpoints:
    def test_scenarios_are_listed(self, client):
        body = client.get("/api/demo/scenarios").json()
        assert [s["key"] for s in body["scenarios"]] == ["A", "B", "C"]
        assert all(s["is_demo_data"] for s in body["scenarios"])
        assert body["dataset_label"]

    def test_load_and_run_a_scenario(self, client):
        bill_id = _bill_id(client.post("/api/demo/scenarios/B/load"))
        analysis = client.post(f"/api/bills/{bill_id}/analyze").json()["analysis"]
        assert analysis["totals"]["bill_total"] > 0
        assert analysis["counts"]["attention"] >= 1
        assert analysis["is_demo_data"] is True

    def test_unknown_scenario_uses_the_error_envelope(self, client):
        response = client.post("/api/demo/scenarios/Z/run")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "scenario_not_found"
        assert "A, B and C" in body["error"]["message"]

    def test_sample_bills_are_listed_without_exposing_uploads(self, client):
        body = client.get("/api/demo/sample-bills").json()
        assert body["files"]
        # Sample documents are generated on demand and listed, never served
        # back as a download route that could be pointed at real uploads.
        for entry in body["files"]:
            assert {"filename", "size_bytes", "format", "scenario"} == set(entry)


class TestErrorEnvelope:
    def test_validation_error_shape(self, client):
        body = client.post("/api/bills", json={"items": []}).json()
        assert "error" in body
        assert set(body["error"]) >= {"code", "message"}

    def test_unhandled_errors_do_not_leak_internals(self, client):
        response = client.get("/api/bills/%20")  # odd id
        assert response.status_code < 500
        if response.status_code >= 400:
            assert "Traceback" not in response.text
