"""Common response envelopes and shared value objects."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApiError(BaseModel):
    code: str
    message: str
    detail: str | None = None
    hint: str | None = None


class ErrorResponse(BaseModel):
    error: ApiError


class ErrorEnvelope(BaseModel, Generic[T]):  # type: ignore[misc]
    """Kept for documentation purposes; the runtime payload is ``ErrorResponse``."""

    error: ApiError


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    demo_mode: bool
    database: str
    ai_provider: str
    ai_provider_ready: bool
    ai_provider_is_real: bool
    ai_fallback_enabled: bool
    benchmark_records: int
    benchmark_label: str
    max_upload_size_mb: int
    raw_file_retention_minutes: int
    auth_enabled: bool
    server_time: str


class DisclaimerResponse(BaseModel):
    main: str
    tool_notice: str
    dataset_notice: str
    privacy_notice: str
