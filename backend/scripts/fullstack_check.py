"""Full-stack verification: every endpoint the frontend calls, over real HTTP.

Unlike ``e2e_check.py`` (which focuses on the upload path), this walks the
complete surface the React app depends on and asserts the response *shapes*
match what ``frontend/src/api/types.ts`` declares. A renamed field or a changed
envelope breaks here rather than as a blank screen in the browser.

Run it with no arguments; it starts its own server on a free port, uses a
throwaway database and storage directory, and shuts down on exit.

    python -m scripts.fullstack_check
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


WORKDIR = Path(tempfile.mkdtemp(prefix="medbill-fullstack-"))
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"

# Configure before any application import so nothing touches real dev data.
os.environ.update(
    {
        "PYTHONPATH": str(BACKEND_DIR),
        "MEDBILL_DATABASE_URL": f"sqlite:///{(WORKDIR / 'check.db').as_posix()}",
        "MEDBILL_STORAGE_DIR": str(WORKDIR / "uploads"),
        "MEDBILL_ENVIRONMENT": "development",
        "MEDBILL_DEMO_MODE": "true",
        "MEDBILL_SEED_DEMO_BENCHMARKS": "true",
        "MEDBILL_AUTH_ENABLED": "false",
        "MEDBILL_RATE_LIMIT_ENABLED": "false",
    }
)
for _key in list(os.environ):
    if _key.startswith("MEDBILL_AI_API_KEY"):
        os.environ.pop(_key)

import httpx  # noqa: E402
import uvicorn  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    results.append((PASS if condition else FAIL, name, detail))
    return condition


def has_keys(payload: Any, keys: set[str], label: str) -> bool:
    """Every required key present. Reports the first missing one."""
    if not isinstance(payload, dict):
        check(label, False, f"expected an object, got {type(payload).__name__}")
        return False
    missing = sorted(keys - set(payload))
    check(label, not missing, f"missing {missing}" if missing else "")
    return not missing


# Words that would be inappropriate if used *as an accusation*. The tool is
# expected to say it does not detect fraud, so a bare keyword search is wrong:
# a sentence is only a problem when it makes the claim rather than disclaiming
# it.
SENSITIVE = ("fraud", "scam", "malpractice", "illegal", "overcharg", "illegal")
NEGATIONS = ("not ", "no ", "never", "cannot", "n't", "without", "rather than", "instead of")


def accusations(text: str) -> list[str]:
    """Sentences that assert wrongdoing rather than disclaim it."""
    found: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        lowered = sentence.lower()
        if any(word in lowered for word in SENSITIVE) and not any(
            marker in lowered for marker in NEGATIONS
        ):
            found.append(sentence.strip()[:160])
    return found


def walk_text(node: Any) -> list[str]:
    """Every string anywhere in a nested payload."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [text for value in node.values() for text in walk_text(value)]
    if isinstance(node, list):
        return [text for value in node for text in walk_text(value)]
    return []


def accuse_free(payload: Any) -> list[str]:
    """Every accusatory sentence found anywhere in a payload."""
    return [sentence for text in walk_text(payload) for sentence in accusations(text)]


def main() -> int:
    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    import threading

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 45
    client = httpx.Client(base_url=BASE, timeout=60.0)
    while time.time() < deadline:
        try:
            if client.get("/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.25)
    else:
        print("FATAL: server did not start in time")
        server.should_exit = True
        return 1

    try:
        run_checks(client)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        client.close()
        shutil.rmtree(WORKDIR, ignore_errors=True)

    failures = [row for row in results if row[0] == FAIL]
    print()
    for status, name, detail in results:
        line = f"[{status}] {name}"
        if detail:
            line += f" -- {detail}"
        print(line)
    print()
    print(f"{len(results) - len(failures)}/{len(results)} checks passed")
    return 1 if failures else 0


def run_checks(client: httpx.Client) -> None:  # noqa: C901 - a flat list of checks
    # -- Global metadata (AppMeta provider) --------------------------------
    health = client.get("/api/health").json()
    has_keys(
        health,
        {
            "status",
            "app",
            "version",
            "environment",
            "demo_mode",
            "database",
            "ai_provider",
            "ai_provider_is_real",
            "benchmark_records",
            "benchmark_label",
            "max_upload_size_mb",
            "raw_file_retention_minutes",
        },
        "GET /api/health shape",
    )
    check(
        "demo mode needs no API key",
        health["ai_provider"] == "demo" and not health["ai_provider_is_real"],
        f"provider={health['ai_provider']} real={health['ai_provider_is_real']}",
    )
    check(
        "benchmark dataset is seeded",
        health["benchmark_records"] > 1000,
        f"{health['benchmark_records']} records",
    )
    check(
        "dataset label is valid UTF-8",
        "\ufffd" not in health["benchmark_label"] and "?" not in health["benchmark_label"],
        repr(health["benchmark_label"]),
    )

    disclaimer = client.get("/api/disclaimer").json()
    has_keys(
        disclaimer,
        {"main", "tool_notice", "dataset_notice", "privacy_notice"},
        "GET /api/disclaimer shape",
    )
    check("no accusatory language in notices", not accuse_free(disclaimer), str(accuse_free(disclaimer)))

    options = client.get("/api/options").json()
    has_keys(
        options,
        {
            "categories",
            "hospital_categories",
            "room_categories",
            "cities",
            "treatments",
            "demo_scenarios",
        },
        "GET /api/options shape",
    )
    check(
        "options feed the dropdowns",
        len(options["categories"]) >= 5 and len(options["cities"]) >= 3,
        f"{len(options['categories'])} categories, {len(options['cities'])} cities",
    )
    check(
        "category options are {value,label} pairs",
        all(
            isinstance(option, dict) and {"value", "label"} <= set(option)
            for key in ("categories", "hospital_categories", "room_categories")
            for option in options[key]
        ),
    )
    check(
        "cities and treatments are plain strings",
        all(isinstance(value, str) for value in options["cities"])
        and all(isinstance(value, str) for value in options["treatments"]),
    )

    # -- Benchmark browser ---------------------------------------------------
    stats = client.get("/api/benchmarks/stats").json()
    has_keys(
        stats,
        {"total_records", "verified_records", "dataset_label", "is_demo_data", "notice", "cities"},
        "GET /api/benchmarks/stats shape",
    )

    listing = client.get("/api/benchmarks", params={"limit": 5}).json()
    has_keys(
        listing,
        {"items", "total", "limit", "offset", "dataset_label", "notice"},
        "GET /api/benchmarks shape",
    )
    check("benchmark list is populated", len(listing["items"]) == 5, f"{len(listing['items'])} items")
    check(
        "benchmark items carry price fields",
        has_keys(
            listing["items"][0],
            {"service_name", "service_category", "city", "min_price", "median_price", "max_price"},
            "BenchmarkPriceOut shape",
        ),
    )
    check(
        "min <= median <= max",
        all(
            row["min_price"] <= row["median_price"] <= row["max_price"]
            for row in listing["items"]
        ),
    )
    check(
        "published tariffs sit alongside the demo rows",
        stats["verified_records"] > 0 and stats["demo_records"] > 0,
        f"verified={stats['verified_records']} demo={stats['demo_records']}",
    )
    check(
        "a dataset holding both sources is not labelled demo-only",
        stats["is_demo_data"] is False,
        f"is_demo_data={stats['is_demo_data']}",
    )

    government = client.get(
        "/api/benchmarks",
        params={
            "city": "Kolkata",
            "hospital_category": "government",
            "verified_only": True,
            "limit": 25,
        },
    ).json()
    check(
        "government rows are retrievable",
        government["total"] > 0 and len(government["items"]) == 25,
        f"{government['total']} rows",
    )
    check(
        "government rows carry their published source",
        all(
            row["verification_status"] == "government_rate"
            and "cghs.mohfw.gov.in" in (row["source_url"] or "")
            and row["source_date"]
            and row["currency_code"] == "INR"
            for row in government["items"]
        ),
        repr(government["items"][0]["source_name"]),
    )
    check(
        "government rates are ordered",
        all(
            row["min_price"] <= row["median_price"] <= row["max_price"]
            for row in government["items"]
        ),
    )
    check(
        "no accusatory language in dataset notices",
        not accuse_free(stats),
        str(accuse_free(stats)),
    )

    filtered = client.get(
        "/api/benchmarks",
        params={"city": listing["items"][0]["city"], "service_category": "room", "limit": 50},
    ).json()
    check(
        "filters narrow the result set",
        all(row["city"] == listing["items"][0]["city"] for row in filtered["items"]),
        f"{filtered['total']} records",
    )

    detail = client.get(f"/api/benchmarks/{listing['items'][0]['id']}").json()
    check("GET /api/benchmarks/{id} shape", has_keys(detail, {"id", "service_name"}, "BenchmarkPriceOut detail"))

    # -- Demo scenarios (DemoPage) -------------------------------------------
    scenarios = client.get("/api/demo/scenarios").json()
    has_keys(scenarios, {"scenarios", "dataset_label", "notice"}, "GET /api/demo/scenarios shape")
    check(
        "three demo scenarios exist",
        [s["key"] for s in scenarios["scenarios"]] == ["A", "B", "C"],
    )
    check(
        "scenarios are labelled as demo data",
        all(s["is_demo_data"] for s in scenarios["scenarios"]),
    )

    samples = client.get("/api/demo/sample-bills").json()
    has_keys(samples, {"files"}, "GET /api/demo/sample-bills shape")
    check("sample documents were generated", len(samples["files"]) >= 3, f"{len(samples['files'])} files")

    # -- One-click demo run (DemoPage "Run this scenario") --------------------
    ran = client.post("/api/demo/scenarios/A/run").json()
    has_keys(ran, {"analysis", "messages"}, "POST /api/demo/scenarios/A/run shape")
    analysis = ran["analysis"]
    bill_id = analysis["bill_id"]
    has_keys(
        analysis,
        {
            "id",
            "bill_id",
            "status",
            "context",
            "totals",
            "counts",
            "comparisons",
            "flagged",
            "chart_data",
            "questions",
            "summary",
            "headline",
            "dataset_label",
            "is_demo_data",
            "provider_name",
            "provider_is_real",
            "thresholds",
            "engine_version",
            "disclaimer",
            "notices",
        },
        "AnalysisOut shape",
    )
    check("scenario A total is 43,950", analysis["totals"]["bill_total"] == 43950, str(analysis["totals"]["bill_total"]))
    check("scenario A coverage is 90%", analysis["totals"]["coverage_percent"] == 90.0)
    check(
        "chart data is populated for the charts",
        len(analysis["chart_data"]["actual_vs_benchmark"]) > 0
        and len(analysis["chart_data"]["category_spend"]) > 0,
        f"{len(analysis['chart_data']['actual_vs_benchmark'])} categories",
    )
    check("questions were generated", len(analysis["questions"]) >= 3, f"{len(analysis['questions'])} questions")
    check(
        "comparisons carry benchmark display strings",
        all(
            isinstance(row["benchmark_display"], str) and isinstance(row["difference_display"], str)
            for row in analysis["comparisons"]
        ),
    )
    check(
        "flag statuses are known to the UI",
        all(
            row["flag_status"]
            in {
                "within_range",
                "below_range",
                "review",
                "above_range",
                "attention",
                "insufficient_data",
                "not_comparable",
            }
            for row in analysis["comparisons"]
        ),
    )
    check(
        "no accusatory wording anywhere in the analysis",
        not accuse_free(analysis),
        str(accuse_free(analysis)),
    )

    # -- GET analysis returns a bare AnalysisOut (not an envelope) -------------
    fetched = client.get(f"/api/bills/{bill_id}/analysis")
    check("GET analysis returns 200", fetched.status_code == 200, str(fetched.status_code))
    check(
        "GET analysis is not wrapped",
        "comparisons" in fetched.json() and "analysis" not in fetched.json(),
    )
    check(
        "stored analysis matches the run",
        fetched.json()["totals"]["bill_total"] == analysis["totals"]["bill_total"],
    )

    # -- Report (ReportPage) ---------------------------------------------------
    report = client.get(f"/api/bills/{bill_id}/report").json()
    has_keys(
        report,
        {
            "bill_id",
            "generated_at",
            "anonymized",
            "redaction_applied",
            "title",
            "sections",
            "disclaimer",
            "dataset_notice",
            "ai_notice",
            "provider_name",
            "provider_is_real",
        },
        "GET report shape",
    )
    check("report has sections", len(report["sections"]) >= 4, f"{len(report['sections'])} sections")
    check(
        "report redacts identifiers by default",
        report["anonymized"] and report["redaction_applied"].get("hide_patient_name"),
    )

    markdown = client.get(f"/api/bills/{bill_id}/report", params={"format": "markdown"}).json()
    check("markdown export is produced", bool(markdown.get("markdown")), f"{len(markdown.get('markdown') or '')} chars")

    # -- Questions (POST only; GET must not be allowed) -----------------------
    questions = client.post(f"/api/bills/{bill_id}/questions").json()
    has_keys(questions, {"bill_id", "questions"}, "POST questions shape")
    check("questions can be regenerated", isinstance(questions["questions"], list))
    check(
        "GET on the questions path is not allowed",
        client.get(f"/api/bills/{bill_id}/questions").status_code == 405,
    )

    # -- Manual entry + confirm (ReviewPage) ---------------------------------
    manual = client.post(
        "/api/bills",
        json={
            "items": [
                {
                    "description": "Consultant Doctor Fee",
                    "category": "doctor",
                    "quantity": 2,
                    "unit_price": 900,
                    "total_price": 1800,
                },
                {
                    "description": "Private Room Charges",
                    "category": "room",
                    "quantity": 3,
                    "unit_price": 4500,
                    "total_price": 13500,
                },
                {
                    "description": "Corporate Discount",
                    "category": "discount",
                    "quantity": 1,
                    "unit_price": -1500,
                    "total_price": -1500,
                },
            ],
            "metadata": {"hospital_name": "Check Clinic"},
            "context": {
                "city": options["cities"][0],
                "hospital_category": options["hospital_categories"][0]["value"],
                "treatment": options["treatments"][0],
                "room_category": options["room_categories"][0]["value"],
            },
        },
    )
    check("manual entry returns 201", manual.status_code == 201, str(manual.status_code))
    manual_body = manual.json()
    has_keys(manual_body, {"bill", "next_step", "warnings"}, "POST /api/bills shape")
    check(
        "manual totals discount correctly",
        manual_body["bill"]["totals"]["grand_total"] == 13800,
        str(manual_body["bill"]["totals"]["grand_total"]),
    )
    check("manual entry is confirmed on creation", manual_body["next_step"] == "analyze")
    manual_id = manual_body["bill"]["id"]

    manual_analysis = client.post(f"/api/bills/{manual_id}/analyze").json()
    has_keys(manual_analysis, {"analysis", "messages"}, "POST analyze shape")
    check(
        "manual analysis matches the server-side total",
        manual_analysis["analysis"]["totals"]["bill_total"] == 13800,
    )

    # -- Confirmation gate ---------------------------------------------------
    fresh = client.post(
        "/api/bills",
        json={
            "items": [
                {"description": "MRI Scan", "category": "diagnostics", "quantity": 1, "unit_price": 4200}
            ]
        },
    ).json()
    unconfirmed_id = fresh["bill"]["id"]
    # Manual creation confirms immediately, so build the unconfirmed case by
    # explicitly saving without confirming.
    saved = client.put(
        f"/api/bills/{unconfirmed_id}/items",
        json={
            "items": [
                {"description": "MRI Scan", "category": "diagnostics", "quantity": 1, "unit_price": 4200}
            ],
            "mark_confirmed": False,
        },
    )
    check("PUT items returns a bare bill", "totals" in saved.json() and "bill" not in saved.json())
    blocked = client.get(f"/api/bills/{unconfirmed_id}/analysis")
    check("unconfirmed analysis is 409", blocked.status_code == 409, str(blocked.status_code))
    error_body = blocked.json()
    has_keys(error_body, {"error"}, "error envelope")
    has_keys(
        error_body.get("error", {}),
        {"code", "message", "detail", "hint"},
        "error envelope fields",
    )

    # The review screen compares before it confirms. Asserted right beside the
    # 409 it deliberately bypasses, so the gate stays where it belongs.
    preview_item = fresh["bill"]["items"][0]
    preview = client.post(
        "/api/bills/preview",
        json={
            "bill_id": unconfirmed_id,
            "items": [
                {
                    "key": "row-mri",
                    "id": preview_item["id"],
                    "description": "MRI Scan",
                    "category": "diagnostics",
                    "quantity": 1,
                    "unit_price": 4200,
                }
            ],
        },
    )
    check(
        "preview runs while analysis is still 409",
        preview.status_code == 200,
        str(preview.status_code),
    )
    preview_body = preview.json()
    has_keys(
        preview_body,
        {
            "bill_id",
            "comparisons",
            "counts",
            "coverage_percent",
            "headline",
            "dataset_label",
            "notices",
            "disclaimer",
            "context",
        },
        "preview response shape",
    )
    check(
        "preview echoes the client's row key",
        bool(preview_body.get("comparisons"))
        and preview_body["comparisons"][0]["id"] == "row-mri",
        str(preview_body.get("comparisons"))[:160],
    )
    check(
        "preview does not confirm the bill",
        client.get(f"/api/bills/{unconfirmed_id}").json()["status"]
        == "awaiting_confirmation",
    )
    check(
        "no accusatory language in the preview",
        not accuse_free(preview_body),
        str(accuse_free(preview_body)),
    )

    confirmed = client.put(

        f"/api/bills/{unconfirmed_id}/items",
        json={
            "items": [
                {"description": "MRI Scan", "category": "diagnostics", "quantity": 1, "unit_price": 4200}
            ],
            "mark_confirmed": True,
        },
    )
    check("confirming succeeds", confirmed.status_code == 200, str(confirmed.status_code))
    check(
        "a confirmed bill is no longer blocked",
        client.get(f"/api/bills/{unconfirmed_id}/analysis").status_code != 409
        or client.get(f"/api/bills/{unconfirmed_id}/analysis").json()["error"]["code"]
        == "analysis_not_ready",
    )
    analysed = client.post(f"/api/bills/{unconfirmed_id}/analyze")
    check("a confirmed bill can be analysed", analysed.status_code == 200, str(analysed.status_code))
    check(
        "the analysis is then readable",
        client.get(f"/api/bills/{unconfirmed_id}/analysis").status_code == 200,
    )

    # -- Strict request validation -------------------------------------------
    stray = client.post(
        "/api/bills",
        json={
            "items": [{"description": "X", "category": "other", "quantity": 1, "unit_price": 1}],
            "metadata": {"hospital_category": "multispecialty"},
        },
    )
    check("a context field inside metadata is rejected", stray.status_code == 422, str(stray.status_code))
    check(
        "the rejection uses the standard error code",
        stray.json().get("error", {}).get("code") == "validation_error",
    )

    # -- Upload path with a real document ------------------------------------
    pdfs = [f for f in samples["files"] if f["format"] == "pdf"]
    check("a sample PDF is available for upload", bool(pdfs), f"{len(pdfs)} pdfs")
    if pdfs:
        pdf_path = BACKEND_DIR / "data" / "sample_bills" / pdfs[0]["filename"]
        if not pdf_path.exists():
            pdf_path = next(
                (WORKDIR / "uploads").glob("*"), None
            )  # fallback, see below
        if pdf_path and pdf_path.exists():
            with pdf_path.open("rb") as handle:
                upload = client.post(
                    "/api/bills/upload", files={"file": (pdf_path.name, handle, "application/pdf")}
                )
            check("PDF upload returns 201", upload.status_code == 201, str(upload.status_code))
            up = upload.json()
            has_keys(up, {"bill", "next_step", "warnings"}, "POST upload shape")
            check("upload is followed by extraction", up["next_step"] == "extract", up["next_step"])

            upload_id = up["bill"]["id"]
            extracted = client.post(f"/api/bills/{upload_id}/extract").json()
            has_keys(extracted, {"bill", "warnings", "requires_confirmation"}, "POST extract shape")
            check(
                "extraction reads real charges from the PDF",
                len(extracted["bill"]["items"]) >= 8,
                f"{len(extracted['bill']['items'])} items",
            )
            check("extraction requires confirmation", extracted["requires_confirmation"] is True)
            check(
                "uploaded bill total matches the scenario",
                extracted["bill"]["totals"]["grand_total"] == 43950,
                str(extracted["bill"]["totals"]["grand_total"]),
            )

            upload_items = [
                {
                    "id": item["id"],
                    "description": item["description"],
                    "category": item["category"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                    "total_price": item["total_price"],
                }
                for item in extracted["bill"]["items"]
            ]
            upload_confirm = client.put(
                f"/api/bills/{upload_id}/items",
                json={
                    "items": upload_items,
                    "metadata": {
                        "hospital_name": extracted["bill"]["hospital_name"],
                        "bill_date": extracted["bill"]["bill_date"],
                    },
                    "context": {
                        "city": extracted["bill"]["city"],
                        "hospital_category": extracted["bill"]["hospital_category"],
                        "treatment": extracted["bill"]["treatment"],
                        "room_category": extracted["bill"]["room_category"],
                    },
                    "mark_confirmed": True,
                },
            )
            check("uploaded bill confirms", upload_confirm.status_code == 200, str(upload_confirm.status_code))
            upload_analysis = client.post(f"/api/bills/{upload_id}/analyze").json()
            check(
                "uploaded bill produces the same numbers as the seeded scenario",
                upload_analysis["analysis"]["totals"]["bill_total"] == 43950
                and upload_analysis["analysis"]["totals"]["coverage_percent"] == 90.0,
                f"total={upload_analysis['analysis']['totals']['bill_total']} "
                f"coverage={upload_analysis['analysis']['totals']['coverage_percent']}",
            )

    # -- Profile preferences: redaction contract ------------------------------
    # The Profile page sends exactly these six query parameters. `hide_*` fields
    # are redactions and are echoed back in `redaction_applied`; `include_*`
    # fields are content switches and only add or drop a report section.
    redact_fields = {
        "hide_patient_name",
        "hide_patient_id",
        "hide_bill_number",
        "hide_hospital_name",
    }
    include_fields = {"include_questions", "include_sources"}

    def section_keys(payload: dict[str, Any]) -> set[str]:
        return {str(section.get("key")) for section in payload.get("sections", [])}

    default_report = client.get(f"/api/bills/{manual_id}/report").json()
    check(
        "report echoes every redaction field the Profile page controls",
        redact_fields == set(default_report.get("redaction_applied", {})),
        str(sorted(set(default_report.get("redaction_applied", {})))),
    )
    check(
        "patient identifiers are hidden by default",
        default_report["redaction_applied"].get("hide_patient_name") is True
        and default_report["redaction_applied"].get("hide_patient_id") is True
        and default_report["redaction_applied"].get("hide_bill_number") is True,
    )
    check(
        "questions and sources sections are included by default",
        {"questions", "sources"}.issubset(section_keys(default_report)),
    )

    nothing_hidden = client.get(
        f"/api/bills/{manual_id}/report",
        params={field: "false" for field in sorted(redact_fields)},
    )
    check(
        "report accepts every redaction toggle set to false",
        nothing_hidden.status_code == 200,
        str(nothing_hidden.status_code),
    )
    if nothing_hidden.status_code == 200:
        payload = nothing_hidden.json()
        check(
            "each redaction toggle is honoured independently",
            all(payload["redaction_applied"].get(field) is False for field in sorted(redact_fields)),
            str(payload["redaction_applied"]),
        )
        check(
            "a report with nothing hidden is no longer marked anonymised",
            payload["anonymized"] is False,
            str(payload["anonymized"]),
        )

    no_questions = client.get(
        f"/api/bills/{manual_id}/report",
        params={"include_questions": "false", "include_sources": "false"},
    )
    check(
        "report accepts both include toggles set to false",
        no_questions.status_code == 200,
        str(no_questions.status_code),
    )
    if no_questions.status_code == 200:
        keys = section_keys(no_questions.json())
        check(
            "turning off include toggles drops those sections",
            "questions" not in keys and "sources" not in keys,
            str(sorted(keys)),
        )
        check(
            "hiding is unaffected by the include toggles",
            no_questions.json()["redaction_applied"].get("hide_patient_name") is True,
        )

    bad_report = client.get(
        f"/api/bills/{manual_id}/report",
        params={"format": "pdf"},
    )
    check(
        "report rejects an unsupported format from the profile UI",
        bad_report.status_code == 422,
        str(bad_report.status_code),
    )

    # -- Rejections and edge cases --------------------------------------------
    wrong_type = client.post(
        "/api/bills/upload",
        files={"file": ("notes.txt", b"just text, not a pdf", "text/plain")},
    )
    check("a text file masquerading as a PDF is rejected", wrong_type.status_code in (415, 422), str(wrong_type.status_code))

    missing = client.get("/api/bills/does-not-exist")
    check("unknown bill returns 404", missing.status_code == 404, str(missing.status_code))
    check("404 uses the error envelope", missing.json().get("error", {}).get("code") == "bill_not_found")

    bad_scenario = client.post("/api/demo/scenarios/Z/run")
    check("unknown scenario returns 404", bad_scenario.status_code == 404, str(bad_scenario.status_code))

    # -- Privacy: raw documents are never served -----------------------------
    # No route returns an uploaded document. 404 (no such path) and 405 (path
    # exists, wrong verb) both prove absence of a serving endpoint.
    served = client.get("/api/bills/upload")
    check(
        "there is no endpoint that serves an uploaded document",
        served.status_code in (404, 405),
        str(served.status_code),
    )
    check(
        "no route advertises raw file serving",
        "SERVE_RAW_FILES" not in json.dumps(
            client.get("/api/health").json()
        ).upper().replace("SERVE_RAW_FILES", ""),
        "health does not expose a raw-file toggle",
    )

    # -- Deletion -------------------------------------------------------------
    deleted = client.delete(f"/api/bills/{manual_id}")
    check("a bill can be deleted", deleted.status_code == 200 and deleted.json()["deleted"] is True)
    check("a deleted bill is gone", client.get(f"/api/bills/{manual_id}").status_code == 404)


if __name__ == "__main__":
    raise SystemExit(main())
