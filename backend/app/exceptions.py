"""Custom exception hierarchy for IsoCrates."""

from enum import Enum
from typing import Optional, Dict, Any


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""

    # Document errors
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    INVALID_DOCUMENT_PATH = "INVALID_DOCUMENT_PATH"
    DOCUMENT_ALREADY_EXISTS = "DOCUMENT_ALREADY_EXISTS"

    # Version errors
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"

    # Dependency errors
    DEPENDENCY_NOT_FOUND = "DEPENDENCY_NOT_FOUND"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    SELF_DEPENDENCY = "SELF_DEPENDENCY"

    # Folder errors
    FOLDER_NOT_FOUND = "FOLDER_NOT_FOUND"

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # Database errors
    DATABASE_ERROR = "DATABASE_ERROR"

    # Webhook errors
    WEBHOOK_VALIDATION_FAILED = "WEBHOOK_VALIDATION_FAILED"

    # Auth & rate limiting
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"

    # Concurrency errors
    CONFLICT = "CONFLICT"

    # Generic errors
    INTERNAL_ERROR = "INTERNAL_ERROR"


class IsoException(Exception):
    """
    Base exception for all IsoCrates errors.

    Provides structured error responses with:
    - Human-readable message
    - Machine-readable error code
    - HTTP status code
    - Optional additional details
    """

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize exception.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            status_code: HTTP status code to return
            details: Optional additional context/details
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for JSON response.

        Returns:
            Dictionary with error, message, and details fields
        """
        return {
            "error": self.error_code.value,
            "message": self.message,
            "details": self.details
        }


class DocumentNotFoundError(IsoException):
    """Document not found in database."""

    def __init__(self, doc_id: str):
        super().__init__(
            f"Document not found: {doc_id}",
            ErrorCode.DOCUMENT_NOT_FOUND,
            status_code=404,
            details={"doc_id": doc_id}
        )


class VersionNotFoundError(IsoException):
    """Version not found in database."""

    def __init__(self, version_id: str):
        super().__init__(
            f"Version not found: {version_id}",
            ErrorCode.VERSION_NOT_FOUND,
            status_code=404,
            details={"version_id": version_id}
        )


class FolderNotFoundError(IsoException):
    """Folder not found in database."""

    def __init__(self, folder_id: str):
        super().__init__(
            f"Folder not found: {folder_id}",
            ErrorCode.FOLDER_NOT_FOUND,
            status_code=404,
            details={"folder_id": folder_id}
        )


class ValidationError(IsoException):
    """Validation failed for user input."""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else {}
        super().__init__(
            message,
            ErrorCode.VALIDATION_ERROR,
            status_code=400,
            details=details
        )


class CircularDependencyError(IsoException):
    """Creating this dependency would create a circular reference."""

    def __init__(self, from_doc_id: str, to_doc_id: str):
        super().__init__(
            f"Would create circular reference: {from_doc_id} -> {to_doc_id}",
            ErrorCode.CIRCULAR_DEPENDENCY,
            status_code=400,
            details={"from_doc_id": from_doc_id, "to_doc_id": to_doc_id}
        )


class SelfDependencyError(IsoException):
    """Cannot create dependency from document to itself."""

    def __init__(self, doc_id: str):
        super().__init__(
            f"Cannot create self-dependency: {doc_id}",
            ErrorCode.SELF_DEPENDENCY,
            status_code=400,
            details={"doc_id": doc_id}
        )


class WebhookValidationError(IsoException):
    """Webhook signature validation failed."""

    def __init__(self, message: str = "Invalid webhook signature"):
        super().__init__(
            message,
            ErrorCode.WEBHOOK_VALIDATION_FAILED,
            status_code=401,
        )


class AuthenticationError(IsoException):
    """Request lacks valid authentication credentials."""

    def __init__(self, message: str = "Invalid or missing authentication token"):
        super().__init__(
            message,
            ErrorCode.UNAUTHORIZED,
            status_code=401,
        )


class ForbiddenError(IsoException):
    """Authenticated user lacks permission for the requested action."""

    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(
            message,
            ErrorCode.FORBIDDEN,
            status_code=403,
        )


class ConflictError(IsoException):
    """Update conflicts with a concurrent modification."""

    def __init__(self, doc_id: str, message: str = "Document was modified by another user"):
        super().__init__(
            message,
            ErrorCode.CONFLICT,
            status_code=409,
            details={"doc_id": doc_id}
        )


class DatabaseError(IsoException):
    """Database operation failed."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        details = {}
        if original_error:
            details["original_error"] = str(original_error)

        super().__init__(
            message,
            ErrorCode.DATABASE_ERROR,
            status_code=500,
            details=details
        )
