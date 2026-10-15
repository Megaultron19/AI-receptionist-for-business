class DomainError(Exception):
    """A business-rule failure with a message safe to show to staff or customers (and to the AI)."""

    def __init__(self, message: str, code: str = "invalid", status: int = 400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


class NotFound(DomainError):
    def __init__(self, what: str):
        super().__init__(f"{what} not found", "not_found", 404)


class Conflict(DomainError):
    def __init__(self, message: str):
        super().__init__(message, "conflict", 409)
