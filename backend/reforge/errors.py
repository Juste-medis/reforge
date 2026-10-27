"""Typed errors with stable codes, so the API and UI can map failures to guidance."""

from __future__ import annotations


class ReforgeError(Exception):
    """A failure with a machine-readable ``code`` and an optional user-facing ``hint``."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "hint": self.hint}
