"""
The typed error hierarchy (§22.2).

Every error MAYA raises on purpose is a ``MayaError`` carrying a stable code,
a user-facing message, an HTTP status and machine-readable context. The API
renders each as an RFC 9457 problem document and the SDK maps the ``type``
code back onto the same class, so a caller catches ``ContractMismatch`` rather
than parsing a message.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any


class MayaError(Exception):
    """Root of every deliberate MAYA error."""

    code = "maya_error"
    status = 400

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def to_problem(self) -> dict[str, Any]:
        """RFC 9457 problem-detail body."""
        return {
            "type": self.code,
            "title": type(self).__name__,
            "status": self.status,
            "detail": self.message,
            "context": self.context,
        }


class InvalidCursor(MayaError):
    """A paging cursor that was tampered with, belongs to another query, or never was one."""

    code, status = "invalid_cursor", 400


class ValidationFailed(MayaError):
    code, status = "validation_failed", 422


class NotFound(MayaError):
    code, status = "not_found", 404


class NotAuthenticated(MayaError):
    code, status = "not_authenticated", 401


class PermissionDenied(MayaError):
    code, status = "permission_denied", 403


class ConflictError(MayaError):
    code, status = "conflict", 409


class NotApproved(MayaError):
    code, status = "not_approved", 409


class ContractMismatch(MayaError):
    code, status = "contract_mismatch", 422


class QualityCheckFailed(MayaError):
    code, status = "quality_check_failed", 422


class WarrantExpired(MayaError):
    code, status = "warrant_expired", 410


class WarrantSuspended(MayaError):
    code, status = "warrant_suspended", 423


class QuotaExceeded(MayaError):
    code, status = "quota_exceeded", 429


class LicenceBreach(MayaError):
    code, status = "licence_breach", 451


class CapabilityRefused(MayaError):
    """A Type C seam has no acceptable backend (§13.4.1). Never a fallback."""

    code, status = "capability_refused", 503


class ConfigurationError(MayaError):
    code, status = "configuration_error", 500


class IntegrityError(MayaError):
    """Stored or replayed content does not match the hash it was sealed with: an incident,
    never served."""

    code, status = "integrity_error", 500


class LlmUnavailable(MayaError):
    """The configured language model could not be asked; the reason says what to change.
    Here, with the others, so a client that asked for a live evaluation gets this class back."""

    code, status = "llm_unavailable", 503


ERRORS_BY_CODE: dict[str, type[MayaError]] = {
    cls.code: cls
    for cls in (
        MayaError,
        ValidationFailed,
        NotFound,
        NotAuthenticated,
        PermissionDenied,
        ConflictError,
        NotApproved,
        ContractMismatch,
        QualityCheckFailed,
        WarrantExpired,
        WarrantSuspended,
        QuotaExceeded,
        LicenceBreach,
        CapabilityRefused,
        ConfigurationError,
        InvalidCursor,
        IntegrityError,
        LlmUnavailable,
    )
}
