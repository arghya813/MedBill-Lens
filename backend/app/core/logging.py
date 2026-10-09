"""Privacy-conscious logging.

Rules enforced here:
  * No bill text, patient names, patient IDs or bill numbers are ever logged.
  * Only identifiers, counts and timings are logged.
"""

from __future__ import annotations

import logging
import re
import sys

_CONFIGURED = False

_SENSITIVE_KEYS = {
    "patient_name",
    "patient_id",
    "uhid",
    "bill_number",
    "bill_no",
    "name",
    "address",
    "phone",                     
    "email",
    "description",
    "raw_text",
    "text",
    "content",
    "api_key",
    "authorization",
    "file_content",
}

_SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{10}\b"),  # Aadhaar-like
    re.compile(r"\b[A-Z]{2,4}/?\d{4,}\b"),  # bill-like ids
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = {k: "[redacted]" if k.lower() in _SENSITIVE_KEYS else v
                           for k, v in record.args.items()}
        message = record.getMessage()
        for pattern in _SENSITIVE_PATTERNS:
            message = pattern.sub("[redacted]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    for noisy in ("uvicorn.access", "httpx", "httpcore", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    logger = logging.getLogger(name)
    logger.addFilter(RedactingFilter())
    return logger
