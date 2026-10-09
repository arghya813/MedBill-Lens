"""Raw-document lifecycle: temporary storage, automatic deletion, cleanup.

Privacy model
-------------
* Uploaded bytes are written to a directory that is never served statically.
* Every document gets an ``expires_at``. A background sweeper deletes it.
* The extracted text is stored in the same row and deleted at the same time.
* Nothing about the file is written to the application log.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.logging import get_logger
from app.models import RawDocument
from app.repositories.bill_repository import BillRepository

logger = get_logger(__name__)

#: Never treat a path outside the storage root as a valid document location.
_SAFE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}


class PrivacyService:
    def __init__(self, db: Session, config: Settings | None = None):
        self.db = db
        self.config = config or settings

    # -- write ---------------------------------------------------------
    def store(
        self,
        *,
        bill_id: str | None,
        filename: str,
        content: bytes,
        content_type: str,
        sha256: str,
        detected_kind: str,
    ) -> RawDocument:
        root = self.config.storage_path.resolve()
        token = sha256[:16]
        suffix = Path(filename).suffix.lower()
        if suffix not in _SAFE_SUFFIXES:
            suffix = ".pdf" if detected_kind == "pdf" else ".png"
        stored_path = root / f"{token}{suffix}"
        stored_path.write_bytes(content)

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.config.raw_file_retention_minutes
        )
        document = RawDocument(
            bill_id=bill_id,
            original_filename=Path(filename).name[:255],
            stored_path=str(stored_path),
            content_type=content_type[:128],
            size_bytes=len(content),
            sha256=sha256,
            expires_at=expires_at,
        )
        self.db.add(document)
        self.db.flush()
        return document

    def attach(self, document: RawDocument, bill_id: str) -> None:
        document.bill_id = bill_id
        self.db.flush()

    def store_text(self, document: RawDocument, text: str) -> None:
        document.extracted_text = text
        self.db.flush()

    def documents_for(self, bill_id: str) -> list[RawDocument]:
        return list(
            self.db.scalars(select(RawDocument).where(RawDocument.bill_id == bill_id)).all()
        )

    # -- read (never exposed over HTTP) --------------------------------
    def _safe_path(self, stored_path: str) -> Path | None:
        try:
            root = self.config.storage_path.resolve()
            candidate = Path(stored_path).resolve()
            candidate.relative_to(root)
        except (ValueError, OSError):
            return None
        return candidate

    def exists_for(self, document_id: str, bill_id: str) -> bool:
        document = self.db.get(RawDocument, document_id)
        if document is None or document.bill_id != bill_id:
            return False
        path = self._safe_path(document.stored_path)
        return bool(path and path.exists())

    # -- delete --------------------------------------------------------
    def purge(self, document: RawDocument) -> None:
        path = self._safe_path(document.stored_path)
        if path and path.exists():
            try:
                os.remove(path)
            except OSError:  # pragma: no cover - filesystem dependent
                logger.warning("raw_file_delete_failed sha_prefix=%s", document.sha256[:8])
        document.extracted_text = None
        document.deleted_at = datetime.now(timezone.utc)
        document.stored_path = ""
        self.db.flush()

    def purge_bill(self, bill_id: str) -> int:
        count = 0
        for document in self.documents_for(bill_id):
            self.purge(document)
            count += 1
        return count

    def purge_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired = list(
            self.db.scalars(
                select(RawDocument).where(
                    RawDocument.deleted_at.is_(None),
                    RawDocument.expires_at < now,
                )
            ).all()
        )
        for document in expired:
            self.purge(document)
        self.db.commit()
        if expired:
            logger.info("raw_documents_purged count=%s", len(expired))
        return len(expired)

    def purge_orphans(self) -> int:
        """Delete uploaded files with no owning bill (crash recovery)."""
        root = self.config.storage_path.resolve()
        known = {
            Path(p).name
            for (p,) in self.db.execute(select(RawDocument.stored_path)).all()
            if p
        }
        removed = 0
        for path in root.glob("*"):
            if path.is_file() and path.name not in known:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:  # pragma: no cover
                    continue
        return removed

    def sweep_bills(self, older_than_minutes: int) -> int:
        repo = BillRepository(self.db)
        ids = repo.expired_ids(timedelta(minutes=older_than_minutes))
        for bill_id in ids:
            bill = repo.get(bill_id)
            if bill is None:
                continue
            self.purge_bill(bill_id)
            repo.delete(bill)
        if ids:
            logger.info("bills_swept count=%s", len(ids))
        return len(ids)
