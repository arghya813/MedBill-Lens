"""Report generation with explicit, user-controlled redaction.

The report is the artefact a patient shares with a hospital or an insurer, so
PII is hidden by default and the user has to opt in to including it.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.enums import (
    CATEGORY_LABELS,
    DatasetLabel,
    SAFE_DISCLAIMER,
    TOOL_NOTICE,
)
from app.core.errors import AnalysisNotReadyError, BillNotFoundError
from app.repositories.bill_repository import AnalysisRepository, BillRepository
from app.schemas.analysis import AnalysisOut, ReportRequest, ReportResponse
from app.services.analysis_service import AI_NOTICE_DEMO, AnalysisService
from app.utils.money import format_money, format_percent, symbol_for_currency

REDACTION_PLACEHOLDER = "[hidden for sharing]"


class ReportService:
    def __init__(
        self,
        db: Session,
        *,
        config: Settings | None = None,
        provider=None,
    ):
        self.db = db
        self.config = config or settings
        self.bill_repo = BillRepository(db)
        self.analysis_repo = AnalysisRepository(db)
        self.analysis_service = AnalysisService(db, config=self.config, provider=provider)

    def build(self, bill_id: str, request: ReportRequest) -> ReportResponse:
        bill = self.bill_repo.get(bill_id)
        if bill is None:
            raise BillNotFoundError(f"No bill exists with id '{bill_id}'.")
        analysis = self.analysis_repo.get_for_bill(bill_id)
        if analysis is None:
            raise AnalysisNotReadyError(
                "No analysis is available for this bill yet. Confirm the bill data and "
                "run the analysis first."
            )

        symbol = symbol_for_currency(bill.currency_code or self.config.currency_code)
        view = self.analysis_service.to_schema(analysis, questions=[])

        redaction = {
            "hide_patient_name": request.hide_patient_name,
            "hide_patient_id": request.hide_patient_id,
            "hide_bill_number": request.hide_bill_number,
            "hide_hospital_name": request.hide_hospital_name,
        }
        anonymized = any(redaction.values())

        def maybe(value: str | None, hide: bool) -> str | None:
            if value is None:
                return None
            return REDACTION_PLACEHOLDER if hide else value

        sections: list[dict] = []

        sections.append(
            {
                "key": "bill",
                "title": "Bill information",
                "fields": [
                    {"label": "Hospital", "value": maybe(bill.hospital_name, request.hide_hospital_name)},
                    {"label": "Location", "value": bill.hospital_location},
                    {"label": "Patient name", "value": maybe(bill.patient_name, request.hide_patient_name)},
                    {"label": "Patient ID", "value": maybe(bill.patient_id, request.hide_patient_id)},
                    {"label": "Bill number", "value": maybe(bill.bill_number, request.hide_bill_number)},
                    {"label": "Bill date", "value": _date(bill.bill_date)},
                    {"label": "Admission date", "value": _date(bill.admission_date)},
                    {"label": "Discharge date", "value": _date(bill.discharge_date)},
                    {"label": "Length of stay", "value": f"{bill.length_of_stay_days} day(s)" if bill.length_of_stay_days else None},
                    {"label": "Room category", "value": bill.room_category},
                    {"label": "Diagnosis (as printed)", "value": bill.diagnosis},
                    {"label": "City", "value": analysis.city},
                    {"label": "Hospital type", "value": analysis.hospital_category},
                    {"label": "Treatment", "value": analysis.treatment},
                ],
            }
        )

        sections.append(
            {
                "key": "summary",
                "title": "Summary",
                "text": analysis.summary,
                "headline": analysis.headline,
            }
        )

        sections.append(
            {
                "key": "totals",
                "title": "Bill total vs benchmark range",
                "fields": [
                    {"label": "Actual bill", "value": format_money(analysis.bill_total, symbol)},
                    {"label": "Estimated benchmark range", "value": view.totals.benchmark_display},
                    {"label": "Difference", "value": view.totals.difference_display},
                    {"label": "Charges analysed", "value": analysis.items_analyzed},
                    {"label": "Within benchmark range", "value": analysis.items_within_range},
                    {"label": "Above benchmark range", "value": analysis.items_attention + analysis.items_review},
                    {"label": "No sufficient benchmark data", "value": analysis.items_insufficient_data},
                ],
            }
        )

        sections.append(
            {
                "key": "charges",
                "title": "Charge-by-charge comparison",
                "columns": [
                    "Charge",
                    "Actual",
                    "Benchmark range",
                    "Difference",
                    "Status",
                ],
                "rows": [
                    [
                        row.description,
                        format_money(row.actual_amount, symbol),
                        row.benchmark_display,
                        _difference_cell(row),
                        row.flag_label,
                    ]
                    for row in view.comparisons
                ],
            }
        )

        flagged_rows = [row for row in view.comparisons if row.is_flagged]
        if flagged_rows:
            sections.append(
                {
                    "key": "flagged",
                    "title": "Charges that may deserve a closer look",
                    "items": [
                        {
                            "charge": row.description,
                            "status": row.flag_label,
                            "reason": row.flag_reason,
                            "explanation": row.ai_explanation,
                        }
                        for row in flagged_rows
                    ],
                }
            )

        insufficient_rows = [
            row for row in view.comparisons if not row.benchmark_available and row.category not in {"tax", "discount", "insurance"}
        ]
        if insufficient_rows:
            sections.append(
                {
                    "key": "insufficient",
                    "title": "Charges without a comparable benchmark",
                    "items": [
                        {"charge": row.description, "reason": row.flag_reason}
                        for row in insufficient_rows
                    ],
                }
            )

        sections.append(
            {
                "key": "notes",
                "title": "How to read this report",
                "items": [
                    "Numbers are produced by the deterministic MedBill Lens engine — no AI sets benchmark ranges or totals.",
                    "Ranges reflect the spread of comparable benchmarks (min–median–max) for your city and hospital type.",
                    "Flags show when the actual charge is outside that range relative to your tolerances; insufficient data means no comparable benchmark was found.",
                    "Patient identifiers are hidden by default; you can opt in from your redaction settings.",
                ],
            }
        )

        if request.include_sources:
            sources = _collect_sources(analysis)
            sections.append({"key": "sources", "title": "Benchmark sources", "items": sources})

        if request.include_questions:
            sections.append(
                {
                    "key": "questions",
                    "title": "Questions to ask the hospital billing department",
                    "items": _collect_questions(analysis),
                }
            )

        provider_is_real = bool(analysis.provider_is_real)
        ai_notice = (
            "Explanations and questions were generated by the configured AI provider. "
            "All numerical comparisons were produced by the deterministic benchmark "
            "engine, not by the AI."
            if provider_is_real
            else AI_NOTICE_DEMO
        )

        response = ReportResponse(
            bill_id=bill.id,
            generated_at=datetime.now(timezone.utc),
            anonymized=anonymized,
            redaction_applied=redaction,
            title=f"MedBill Lens report — {maybe(bill.hospital_name, request.hide_hospital_name) or 'Hospital bill review'}",
            sections=sections,
            disclaimer=SAFE_DISCLAIMER,
            dataset_notice=(
                DatasetLabel.DEMO.value if analysis.is_demo_data else "Verified public benchmark records"
            ),
            ai_notice=ai_notice,
            provider_name=analysis.provider_name,
            provider_is_real=provider_is_real,
            chart_data=self.analysis_service._charts(analysis, symbol),
        )

        if request.format in {"markdown", "html"}:
            markdown = self._markdown(response, view, analysis, symbol)
            response.markdown = markdown
            if request.format == "html":
                response.html = self._html(response, markdown)
        return response

    # ------------------------------------------------------------------
    def _markdown(
        self, report: ReportResponse, view: AnalysisOut, analysis, symbol: str
    ) -> str:
        lines: list[str] = [f"# {report.title}", ""]
        lines.append(f"_Generated {report.generated_at:%Y-%m-%d %H:%M UTC}_")
        lines.append("")
        if report.anonymized:
            hidden = [k.replace("hide_", "").replace("_", " ") for k, v in report.redaction_applied.items() if v]
            lines.append(
                f"**Redacted for sharing:** {', '.join(hidden)} ({REDACTION_PLACEHOLDER})"
            )
            lines.append("")

        for section in report.sections:
            lines.append(f"## {section['title']}")
            lines.append("")
            if section.get("text"):
                lines.append(section["text"])
                lines.append("")
            if section.get("headline"):
                lines.append(f"_{section['headline']}_")
                lines.append("")
            if section.get("fields"):
                for field in section["fields"]:
                    if field.get("value") in (None, ""):
                        continue
                    lines.append(f"- **{field['label']}:** {field['value']}")
                lines.append("")
            if section.get("columns"):
                lines.append("| " + " | ".join(section["columns"]) + " |")
                lines.append("|" + "|".join("---" for _ in section["columns"]) + "|")
                for row in section["rows"]:
                    lines.append("| " + " | ".join(str(c) for c in row) + " |")
                lines.append("")
            if section.get("items"):
                for item in section["items"]:
                    if isinstance(item, str):
                        lines.append(f"- {item}")
                    else:
                        title = item.get("charge") or item.get("name") or ""
                        detail = item.get("reason") or item.get("explanation") or ""
                        lines.append(f"- **{title}** — {detail}")
                lines.append("")

        lines.append("## Disclaimer")
        lines.append("")
        lines.append(report.disclaimer)
        lines.append("")
        lines.append(f"**Dataset:** {report.dataset_notice}")
        lines.append("")
        lines.append(f"**AI notice:** {report.ai_notice}")
        lines.append("")
        lines.append(f"_{TOOL_NOTICE}_")
        return "\n".join(lines)

    def _html(self, report: ReportResponse, markdown: str) -> str:
        body = html.escape(markdown)
        return (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(report.title)}</title>"
            "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
            "max-width:820px;margin:0 auto;padding:32px 20px;line-height:1.6;color:#0f172a}"
            "pre{white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
            "font-size:13px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;"
            "padding:20px}h1{font-size:22px}</style></head>"
            f"<body><h1>{html.escape(report.title)}</h1><pre>{body}</pre></body></html>"
        )


def _date(value) -> str | None:
    return value.isoformat() if value else None


def _difference_cell(row) -> str:
    if row.difference_from_median is None:
        return "—"
    pct = format_percent(row.percentage_difference)
    return f"{row.difference_display} ({pct})"


def _collect_sources(analysis) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in analysis.results:
        if not row.benchmark_id or not row.source_name:
            continue
        if row.source_name in seen:
            continue
        seen.add(row.source_name)
        out.append(
            {
                "name": row.source_name,
                "url": row.source_url,
                "date": row.source_date.isoformat() if row.source_date else None,
                "verification_status": row.verification_status,
                "dataset_label": row.dataset_label,
            }
        )
    return out


def _collect_questions(analysis) -> list[str]:
    questions: list[str] = []
    for row in analysis.results:
        for question in row.ai_questions or []:
            if question not in questions:
                questions.append(question)
    from app.providers.demo import _BILL_QUESTIONS

    for question in _BILL_QUESTIONS:
        if question not in questions:
            questions.append(question)
    return questions


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)
