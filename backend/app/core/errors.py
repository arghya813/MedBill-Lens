"""Domain error types mapped to friendly, user-facing messages."""

from __future__ import annotations


class MedBillError(Exception):
    """Base class for all expected application errors."""

    status_code: int = 400
    code: str = "bad_request"
    user_message: str = "Something went wrong while processing your request."

    def __init__(
        self,
        detail: str | None = None,
        *,
        hint: str | None = None,
        code: str | None = None,
        user_message: str | None = None,
        status_code: int | None = None,
    ):
        self.detail = detail or self.__doc__ or self.user_message
        self.hint = hint
        # Per-instance overrides let a generic error carry a specific code and
        # message without every call site having to define a new subclass.
        if code is not None:
            self.code = code
        if user_message is not None:
            self.user_message = user_message
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.detail)

    def to_payload(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.user_message,
                "detail": self.detail,
                "hint": self.hint,
            }
        }


class InvalidFileTypeError(MedBillError):
    status_code = 415
    code = "unsupported_file_type"
    user_message = "That file type is not supported. Please upload a PDF, JPG or PNG file."


class FileTooLargeError(MedBillError):
    status_code = 413
    code = "file_too_large"
    user_message = "That file is too large to process."


class CorruptDocumentError(MedBillError):
    status_code = 422
    code = "corrupt_document"
    user_message = (
        "We couldn't read this document. It may be corrupted or password protected."
    )


class ExtractionFailedError(MedBillError):
    status_code = 422
    code = "extraction_failed"
    user_message = (
        "We couldn't reliably read this bill. Please upload a clearer image or "
        "enter the charges manually."
    )


class NoChargesFoundError(MedBillError):
    status_code = 422
    code = "no_charges_found"
    user_message = (
        "We couldn't find any chargeable line items in this document. "
        "Please upload a clearer copy or enter the charges manually."
    )


class BillNotFoundError(MedBillError):
    status_code = 404
    code = "bill_not_found"
    user_message = "We couldn't find that bill. It may have expired and been removed."


class AnalysisNotReadyError(MedBillError):
    status_code = 409
    code = "analysis_not_ready"
    user_message = (
        "The bill data has not been confirmed yet. Please review and confirm the "
        "extracted charges first."
    )


class BillNotConfirmedError(AnalysisNotReadyError):
    code = "bill_not_confirmed"
    user_message = (
        "The bill data has not been confirmed yet. Please review the extracted "
        "charges and confirm them before running the analysis."
    )


class RateLimitError(MedBillError):
    status_code = 429
    code = "rate_limited"
    user_message = "Too many requests. Please wait a moment and try again."


class ProviderError(MedBillError):
    status_code = 503
    code = "provider_error"
    user_message = (
        "The analysis provider is temporarily unavailable. You can retry, or "
        "continue in demo mode with reduced AI-assisted detail."
    )


class NotImplementedYetError(MedBillError):
    status_code = 501
    code = "not_implemented"
    user_message = "This feature is not available yet."
