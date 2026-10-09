"""Developer smoke script: exercise the whole pipeline without a browser.

    python -m scripts.smoke
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import settings
from app.db.session import SessionLocal, init_db
from app.services.analysis_service import AnalysisService
from app.services.bill_service import BillService
from app.services.report_service import ReportService
from app.services.seeding import create_scenario_bill, seed_benchmarks
from app.schemas.analysis import ReportRequest

sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    init_db()
    with SessionLocal() as db:
        print(f"seeded benchmarks: {seed_benchmarks(db)}")
        for key in ("A", "B", "C"):
            bill = create_scenario_bill(db, key)
            service = BillService(db, config=settings)
            view = service.to_schema(service.repo.get(bill.id))
            print("\n" + "=" * 100)
            print(
                f"SCENARIO {key}: {view.hospital_name} | total {view.totals.grand_total:,.0f} "
                f"| items {len(view.items)}"
            )
            analysis_service = AnalysisService(db, config=settings)
            analysis = asyncio.run(analysis_service.run(bill.id))
            questions = asyncio.run(analysis_service.bill_questions(bill.id))
            out = analysis_service.to_schema(analysis, questions=questions)
            print(f"  benchmark range : {out.totals.benchmark_display}")
            print(f"  difference      : {out.totals.difference_display}")
            print(f"  coverage        : {out.totals.coverage_percent}%")
            print(f"  counts          : {out.counts.model_dump()}")
            print(f"  headline        : {out.headline}")
            print(f"  summary         : {out.summary}")
            for comparison in out.comparisons:
                print(
                    f"    {comparison.description[:36]:<38}{comparison.actual_amount:>10,.0f}"
                    f" | {comparison.benchmark_display:>26}"
                    f" | {comparison.flag_status:<17} | above%={comparison.percentage_above_max}"
                )
            if out.flagged:
                first = out.flagged[0]
                print(f"  explanation     : {first.ai_explanation}")
                print(f"  questions       : {first.ai_questions[:2]}")
            report = ReportService(db, config=settings).build(bill.id, ReportRequest(format="markdown"))
            print(f"  report sections : {[s['key'] for s in report.sections]}")
            print(f"  anonymized      : {report.anonymized}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
