"""Deterministic text layer extraction.

Runs before any provider is consulted, so that every provider (including the
offline demo one) has something to work with:

  * PDF  -> text pulled from the embedded text layer with ``pypdf``.
  * Image -> no text layer exists. If ``pytesseract`` happens to be installed
    and configured it is used opportunistically; otherwise the document is
    flagged so the caller can fall back to vision or manual entry.

This module is provider-agnostic on purpose: it contains no AI calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

from app.core.logging import get_logger
from app.providers.base import DocumentInput

logger = get_logger(__name__)

_MAX_PAGES = 25
_MAX_CHARS = 120_000


@dataclass(slots=True)
class TextExtraction:
    text: str
    page_count: int
    has_text_layer: bool
    ocr_used: bool = False
    ocr_available: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.text)


def _tesseract_available() -> bool:
    try:  # pragma: no cover - environment dependent
        import pytesseract  # type: ignore

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_pdf_text(data: bytes) -> TextExtraction:
    from pypdf import PdfReader

    warnings: list[str] = []
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return TextExtraction(
                    text="",
                    page_count=0,
                    has_text_layer=False,
                    warnings=["PDF is password protected."],
                )
        pages = list(reader.pages)[:_MAX_PAGES]
    except Exception as exc:
        logger.warning("pdf_text_layer_failed detail=%s", type(exc).__name__)
        return TextExtraction(
            text="",
            page_count=0,
            has_text_layer=False,
            warnings=["The PDF could not be opened."],
        )

    chunks: list[str] = []
    for index, page in enumerate(pages):
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
        if sum(len(c) for c in chunks) > _MAX_CHARS:
            warnings.append("Only the first part of the document was read.")
            break

    text = "\n".join(chunks)
    if len(pages) > _MAX_PAGES:
        warnings.append(f"Document has {len(reader.pages)} pages; the first {_MAX_PAGES} were read.")

    has_text = len(text.strip()) >= 40
    ocr_used = False
    if not has_text:
        warnings.append(
            "This PDF looks like a scanned image with no text layer. "
            "Clearer scans or manual entry are recommended."
        )
    return TextExtraction(
        text=text[:_MAX_CHARS],
        page_count=len(pages),
        has_text_layer=has_text,
        ocr_used=ocr_used,
        warnings=warnings,
    )


def extract_image_text(data: bytes) -> TextExtraction:
    ocr_available = _tesseract_available()
    if not ocr_available:
        return TextExtraction(
            text="",
            page_count=1,
            has_text_layer=False,
            ocr_available=False,
            warnings=[
                "No local OCR engine is installed, so the image text was not read "
                "automatically. A vision-capable AI provider is required, or you can "
                "enter the charges manually."
            ],
        )

    import io  # pragma: no cover - optional dependency path

    try:  # pragma: no cover - optional dependency path
        import pytesseract  # type: ignore
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            text = pytesseract.image_to_string(image)
        return TextExtraction(
            text=text[:_MAX_CHARS],
            page_count=1,
            has_text_layer=len(text.strip()) >= 40,
            ocr_used=True,
            ocr_available=True,
            warnings=[] if text.strip() else ["OCR produced no readable text."],
        )
    except Exception as exc:
        logger.warning("ocr_failed detail=%s", type(exc).__name__)
        return TextExtraction(
            text="",
            page_count=1,
            has_text_layer=False,
            ocr_available=True,
            warnings=["The image could not be read by the local OCR engine."],
        )


def extract_text_for(document: DocumentInput) -> TextExtraction:
    if document.text:
        return TextExtraction(
            text=document.text,
            page_count=1,
            has_text_layer=True,
        )
    data = document.bytes_for_extraction
    if data is None:
        return TextExtraction(text="", page_count=0, has_text_layer=False)
    if document.kind == "pdf":
        return extract_pdf_text(data)
    return extract_image_text(data)
