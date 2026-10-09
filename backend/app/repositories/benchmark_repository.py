"""Data access for the benchmark dataset."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BenchmarkPrice


@dataclass(slots=True)
class BenchmarkPage:
    records: list[BenchmarkPrice]
    total: int


class BenchmarkRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, benchmark_id: str) -> BenchmarkPrice | None:
        return self.db.get(BenchmarkPrice, benchmark_id)

    def count(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(BenchmarkPrice)) or 0)

    def count_verified(self) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(BenchmarkPrice)
                .where(BenchmarkPrice.verification_status != "demo")
            )
            or 0
        )

    def search(
        self,
        *,
        city: str | None = None,
        hospital_category: str | None = None,
        service_category: str | None = None,
        treatment: str | None = None,
        room_category: str | None = None,
        country_code: str | None = None,
        verified_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> BenchmarkPage:
        conditions = []
        if city:
            conditions.append(BenchmarkPrice.city == city)
        if country_code:
            conditions.append(BenchmarkPrice.country_code == country_code)
        if hospital_category:
            conditions.append(BenchmarkPrice.hospital_category == hospital_category)
        if service_category:
            conditions.append(BenchmarkPrice.service_category == service_category)
        if treatment:
            conditions.append(BenchmarkPrice.treatment == treatment)
        if room_category:
            conditions.append(BenchmarkPrice.room_category == room_category)
        if verified_only:
            conditions.append(BenchmarkPrice.verification_status != "demo")

        base = select(BenchmarkPrice)
        if conditions:
            base = base.where(*conditions)
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        stmt = base.order_by(
            BenchmarkPrice.city,
            BenchmarkPrice.hospital_category,
            BenchmarkPrice.service_category,
            BenchmarkPrice.service_name,
        ).limit(limit).offset(offset)
        return BenchmarkPage(records=list(self.db.scalars(stmt).all()), total=total)

    def all(self) -> list[BenchmarkPrice]:
        return list(self.db.scalars(select(BenchmarkPrice)).all())

    def distinct(self, column) -> list[str]:
        stmt = select(column).distinct().order_by(column)
        return [v for v in self.db.scalars(stmt).all() if v]

    def stats(self) -> dict:
        return {
            "cities": self.distinct(BenchmarkPrice.city),
            "hospital_categories": self.distinct(BenchmarkPrice.hospital_category),
            "service_categories": self.distinct(BenchmarkPrice.service_category),
            "sources": self.distinct(BenchmarkPrice.source_name),
            "min_source_date": self.db.scalar(select(func.min(BenchmarkPrice.source_date))),
            "max_source_date": self.db.scalar(select(func.max(BenchmarkPrice.source_date))),
        }

    def insert_many(self, records: list[dict]) -> int:
        """Bulk-insert a fresh dataset (no per-row lookup)."""
        from app.models import _uuid

        rows = []
        for payload in records:
            row = dict(payload)
            row.setdefault("id", _uuid())
            rows.append(row)
        self.db.bulk_insert_mappings(BenchmarkPrice, rows)
        self.db.flush()
        return len(rows)

    def upsert_many(self, records: list[dict]) -> int:
        written = 0
        for payload in records:
            key = (
                payload["city"],
                payload["hospital_category"],
                payload["service_name"],
            )
            existing = self.db.scalars(
                select(BenchmarkPrice).where(
                    BenchmarkPrice.city == key[0],
                    BenchmarkPrice.hospital_category == key[1],
                    BenchmarkPrice.service_name == key[2],
                )
            ).first()
            if existing is None:
                self.db.add(BenchmarkPrice(**payload))
            else:
                for field, value in payload.items():
                    setattr(existing, field, value)
            written += 1
        self.db.flush()
        return written

    def clear_demo(self) -> int:
        records = list(
            self.db.scalars(
                select(BenchmarkPrice).where(BenchmarkPrice.verification_status == "demo")
            ).all()
        )
        for record in records:
            self.db.delete(record)
        self.db.flush()
        return len(records)
