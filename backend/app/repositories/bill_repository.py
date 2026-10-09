"""Data access for bills and line items."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import BillStatus
from app.models import Analysis, Bill, BillItem, ChargeComparison, RawDocument


class BillRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **values) -> Bill:
        bill = Bill(**values)
        self.db.add(bill)
        self.db.flush()
        return bill

    def get(self, bill_id: str) -> Bill | None:
        stmt = (
            select(Bill)
            .where(Bill.id == bill_id)
            .options(selectinload(Bill.items), selectinload(Bill.analysis))
        )
        return self.db.scalars(stmt).unique().first()

    def get_with_items(self, bill_id: str) -> Bill | None:
        stmt = (
            select(Bill)
            .where(Bill.id == bill_id)
            .options(selectinload(Bill.items), selectinload(Bill.analysis))
        )
        return self.db.scalars(stmt).unique().first()

    def replace_items(self, bill: Bill, items: list[BillItem]) -> list[BillItem]:
        for existing in list(bill.items):
            self.db.delete(existing)
        self.db.flush()
        created: list[BillItem] = []
        for position, item in enumerate(items):
            created.append(BillItem(bill_id=bill.id, position=position, **item))
        self.db.add_all(created)
        self.db.flush()
        self.db.refresh(bill)
        return created

    def update(self, bill: Bill, **values) -> Bill:
        for key, value in values.items():
            setattr(bill, key, value)
        self.db.flush()
        return bill

    def set_status(self, bill: Bill, status: str) -> Bill:
        bill.status = status
        self.db.flush()
        return bill

    def confirm(self, bill: Bill) -> Bill:
        bill.status = BillStatus.CONFIRMED.value
        bill.confirmed_at = datetime.now(timezone.utc)
        self.db.flush()
        return bill

    def delete(self, bill: Bill) -> None:
        self.db.delete(bill)
        self.db.flush()

    def expired_ids(self, older_than: timedelta) -> list[str]:
        cutoff = datetime.now(timezone.utc) - older_than
        stmt = select(Bill.id).where(
            Bill.created_at < cutoff,
            Bill.status.in_([BillStatus.UPLOADED.value, BillStatus.EXTRACTING.value]),
        )
        return list(self.db.scalars(stmt))


class AnalysisRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_bill(self, bill_id: str) -> Analysis | None:
        stmt = (
            select(Analysis)
            .where(Analysis.bill_id == bill_id)
            .options(selectinload(Analysis.results))
        )
        return self.db.scalars(stmt).unique().first()

    def get(self, analysis_id: str) -> Analysis | None:
        stmt = (
            select(Analysis)
            .where(Analysis.id == analysis_id)
            .options(selectinload(Analysis.results))
        )
        return self.db.scalars(stmt).unique().first()

    def replace_for_bill(self, bill: Bill, **values) -> Analysis:
        existing = self.get_for_bill(bill.id)
        if existing is not None:
            self.db.execute(
                delete(ChargeComparison).where(ChargeComparison.analysis_id == existing.id)
            )
            for key, value in values.items():
                setattr(existing, key, value)
            self.db.flush()
            return existing
        analysis = Analysis(bill_id=bill.id, **values)
        self.db.add(analysis)
        self.db.flush()
        return analysis

    def clear_for_bill(self, bill_id: str) -> None:
        analysis = self.get_for_bill(bill_id)
        if analysis is not None:
            self.db.delete(analysis)
            self.db.flush()

    def add_results(self, analysis: Analysis, results: list[dict]) -> list[ChargeComparison]:
        rows = [
            ChargeComparison(analysis_id=analysis.id, **payload) for payload in results
        ]
        self.db.add_all(rows)
        self.db.flush()
        return rows
