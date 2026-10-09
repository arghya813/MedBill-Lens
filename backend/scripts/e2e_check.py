"""End-to-end check of the real upload path with a bundled sample bill.

Runs outside pytest: uploads the generated scenario A PDF over HTTP, runs
extraction, confirmation, analysis and the report, then checks the numbers
against the scenario's own fixture values.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="medbill-e2e-"))
os.environ["MEDBILL_DATABASE_URL"] = f"sqlite:///{(_TMP / 'e2e.db').as_posix()}"
os.environ["MEDBILL_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["MEDBILL_AI_PROVIDER"] = "demo"
os.environ["MEDBILL_RATE_LIMIT_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.services.sample_documents import bill_lines, build_pdf  # noqa: E402

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    ok = actual == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {actual!r}" + ("" if ok else f" != {expected!r}"))
    if not ok:
        failures.append(label)


with TestClient(create_app()) as client:
    print("health:", client.get("/api/health").json()["status"])

    pdf = build_pdf(bill_lines("A"))
    print("\nupload scenario A PDF over HTTP")
    response = client.post(
        "/api/bills/upload",
        files={"file": ("bill_A.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    check("upload status", response.status_code, 201)
    bill = response.json()["bill"]
    bill_id = bill["id"]
    check("upload state", bill["status"], "uploaded")
    check("no items before extraction", len(bill["items"]), 0)

    print("\nextract")
    response = client.post(f"/api/bills/{bill_id}/extract")
    check("extract status", response.status_code, 200)
    extracted = response.json()["bill"]
    check("extract state", extracted["status"], "awaiting_confirmation")
    check("charges found", len(extracted["items"]), 11)
    check("provider", extracted["extraction"]["provider"], "demo")
    check("method", extracted["extraction"]["method"], "deterministic_rules")
    check("text layer read", extracted["extraction"]["text_length"] > 500, True)
    check("no OCR for a PDF", extracted["extraction"]["ocr_used"], False)
    check(
        "metadata parsed",
        (
            extracted["hospital_name"],
            extracted["bill_number"],
            extracted["room_category"],
            extracted["length_of_stay_days"],
            extracted["bill_date"],
        ),
        ("Sunrise Multispecialty Hospital (Demo)", "DEMO-A-2026-0142", "private", 5, "2026-02-18"),
    )
    room = next(i for i in extracted["items"] if i["description"] == "Private Room Charges")
    check("room qty", room["quantity"], 5.0)
    check("room unit price", room["unit_price"], 4700.0)
    check("room total", room["total_price"], 23500.0)

    print("\nconfirm + analyse")
    payload = {
        "items": [
            {
                "description": i["description"],
                "category": i["category"],
                "quantity": i["quantity"],
                "unit_price": i["unit_price"],
                "total_price": i["total_price"],
            }
            for i in extracted["items"]
        ],
        "metadata": {"hospital_name": extracted["hospital_name"]},
        # Context, not metadata: these fields select which benchmark records
        # are comparable and are rejected as unknown keys in ``metadata``.
        "context": {
            "city": "Kolkata",
            "hospital_category": "multispecialty",
            "treatment": "Internal Medicine",
            "room_category": "private",
        },
        "mark_confirmed": True,
    }
    response = client.put(f"/api/bills/{bill_id}/items", json=payload)
    check("confirm status", response.status_code, 200)
    check("confirmed state", response.json()["status"], "confirmed")

    wrong = dict(payload, metadata={"hospital_category": "multispecialty"})
    check(
        "context field in metadata is rejected",
        client.put(f"/api/bills/{bill_id}/items", json=wrong).status_code,
        422,
    )

    response = client.post(f"/api/bills/{bill_id}/analyze")
    check("analyse status", response.status_code, 200)
    analysis = response.json()["analysis"]
    check("bill total", analysis["totals"]["bill_total"], 43950.0)
    check("coverage", analysis["totals"]["coverage_percent"], 90.0)
    check("within range", analysis["counts"]["within_range"], 9)
    check("insufficient data", analysis["counts"]["insufficient_data"], 1)
    # The GST row is read as a tax total rather than a zero-value charge, so
    # the uploaded bill yields one fewer line item than the scenario fixture.
    check("comparisons produced", len(analysis["comparisons"]), 11)
    check("demo labelled", analysis["is_demo_data"], True)
    check("disclaimer present", bool(analysis["disclaimer"]), True)
    spend = analysis["chart_data"]["category_spend"]
    check("spend chart has categories", len(spend) > 0, True)
    check(
        "spend chart rows carry labels for the graph axis",
        all(row["label"] and row["percent_of_bill"] is not None for row in spend),
        True,
    )

    print("\nreport + questions")
    response = client.get(f"/api/bills/{bill_id}/report", params={"format": "json"})
    check("report status", response.status_code, 200)
    report = response.json()
    check("report anonymised", report["anonymized"], True)
    keys = [section["key"] for section in report["sections"]]
    print(f"        sections: {keys}")
    for required in ("bill", "summary", "totals", "charges", "sources"):
        check(f"section {required}", required in keys, True)
    check("report carries chart data", bool(report["chart_data"]), True)
    check(
        "report spend chart matches the analysis",
        len(report["chart_data"]["category_spend"]) == len(spend),
        True,
    )

    response = client.post(f"/api/bills/{bill_id}/questions")
    check("questions status", response.status_code, 200)
    print(f"        {len(response.json().get('questions', []))} questions returned")

    print("\ncomparison detail")
    for row in analysis["comparisons"]:
        print(
            f"        {row['description'][:38]:<38} {row.get('category', '-'):<14} "
            f"{row['actual_amount']:>10} {row['flag_status']:<18} "
            f"bench={row.get('benchmark_min')}-{row.get('benchmark_max')} "
            f"scaled={row.get('scaled_unit_price')} qty={row.get('quantity')} "
            f"above%={row.get('percentage_above_max')}"
        )
    print(f"        context: {analysis['context']}")
    print(f"        thresholds: {analysis['thresholds']}")

    print("\nprivacy: raw document is not retrievable")
    for path in ("document", "raw", "file"):
        check(f"/{path} not served", client.get(f"/api/bills/{bill_id}/{path}").status_code, 404)

print()
if failures:
    print(f"E2E FAILED: {failures}")
    raise SystemExit(1)
print("E2E OK - upload -> extract -> confirm -> analyse -> report")
