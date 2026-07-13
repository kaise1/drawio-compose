from __future__ import annotations


class DrawioComposeError(Exception):
    """Base exception for expected command failures."""


class ValidationError(DrawioComposeError):
    """One or more user-correctable validation failures."""

    def __init__(self, messages: list[str] | tuple[str, ...] | str):
        if isinstance(messages, str):
            self.messages = [messages]
        else:
            self.messages = list(messages)
        super().__init__("\n".join(self.messages))
