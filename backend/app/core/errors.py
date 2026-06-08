class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, code: str = "app_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(f"{resource} '{resource_id}' not found", code="not_found")


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="validation_error")


class StorageError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="storage_error")
