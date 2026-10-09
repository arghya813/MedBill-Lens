"""Upload validation: type sniffing, size limits, structural sanity checks."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO

from app.core.config import Settings
from app.core.errors import (
    CorruptDocumentError,
    FileTooLargeError,
    InvalidFileTypeError,
)

PDF_MAGIC = b"%PDF-"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

#: MIME types browsers actually send. The *content* is still sniffed, this is
#: only a first-line filter that produces a nicer error message.
ALLOWED_MIME_PREFIXES = ("application/pdf", "image/jpeg", "image/jpg", "image/png")

_MAX_IMAGE_PIXELS = 60_000_000  # decompression-bomb guard


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    content_type: str
    size_bytes: int
    detected_kind: str  # "pdf" | "image"
    sha256: str


def _extension(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def _sniff(content: bytes) -> str | None:
    if content.startswith(PDF_MAGIC):
        return "pdf"
    if content.startswith(PNG_MAGIC):
        return "image"
    if content.startswith(JPEG_MAGIC):
        return "image"
    return None


def validate_upload(
    filename: str,
    content: bytes,
    declared_content_type: str | None,
    settings: Settings,
) -> ValidatedUpload:
    """Validate a raw upload. Raises a :class:`MedBillError` subclass on failure."""
    import hashlib

    filename = (filename or "bill").strip() or "bill"
    ext = _extension(filename)

    if not content:
        raise CorruptDocumentError("The uploaded file was empty.")

    if len(content) > settings.max_upload_bytes:
        raise FileTooLargeError(
            f"File is {len(content) / 1024 / 1024:.1f} MB; the limit is "
            f"{settings.max_upload_size_mb} MB."
        )

    kind = _sniff(content)
    if kind is None:
        raise InvalidFileTypeError(
            f"File '{filename}' was not recognised as PDF, JPG or PNG."
        )

    if ext and ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(
            f"Extension '{ext}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    if not ext:
        raise InvalidFileTypeError(
            f"File '{filename}' has no extension. Rename it to .pdf, .jpg or .png."
        )

    if declared_content_type and not declared_content_type.lower().startswith(
        ALLOWED_MIME_PREFIXES
    ):
        raise InvalidFileTypeError(
            f"Declared content type '{declared_content_type}' is not allowed."
        )

    if kind == "pdf":
        _validate_pdf(content)
    else:
        _validate_image(content)

    return ValidatedUpload(
        filename=filename,
        content_type=declared_content_type or ("application/pdf" if kind == "pdf" else "image/*"),
        size_bytes=len(content),
        detected_kind=kind,
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _validate_pdf(content: bytes) -> None:
    if not content.rstrip().endswith(b"%%EOF"):
        # Truncated / partially-uploaded PDFs are the most common corruption.
        raise CorruptDocumentError("The PDF appears to be incomplete or corrupted.")
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # pragma: no cover - depends on pypdf internals
                raise CorruptDocumentError(
                    "The PDF is password protected. Please upload an unlocked copy."
                ) from exc
        _ = len(reader.pages)
    except CorruptDocumentError:
        raise
    except Exception as exc:
        raise CorruptDocumentError(f"Could not parse the PDF: {exc}") from exc


def _validate_image(content: bytes) -> None:
    try:
        from PIL import Image

        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > _MAX_IMAGE_PIXELS:
                raise CorruptDocumentError(
                    "The image resolution is too large to process safely."
                )
    except CorruptDocumentError:
        raise
    except Exception as exc:
        raise CorruptDocumentError(f"Could not read the image: {exc}") from exc


_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
]


def looks_like_pdf_or_image_bytes(data: bytes) -> bool:
    if _sniff(data) is not None:
        return True
    if data[:2] in (b"PK",):  # docx/xlsx - explicitly rejected, checked for a nicer message
        return False
    return False


def is_zip_based_office_file(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            return any(n.startswith("word/") or n.startswith("xl/") for n in zf.namelist())
    except Exception:
        return False
