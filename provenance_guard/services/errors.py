"""Service-layer exceptions."""


class SubmitValidationError(Exception):
    """Validation error that maps directly to an HTTP response."""

    def __init__(self, code, message, status_code):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
