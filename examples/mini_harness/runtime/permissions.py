"""A minimal permission boundary for the example harness."""
from __future__ import annotations


class PermissionPolicy:
    def __init__(self, allowed_prefixes) -> None:
        self.allowed_prefixes = tuple(allowed_prefixes)

    def authorize(self, command: str) -> bool:
        if not isinstance(command, str):
            raise TypeError("command must be a string")
        return command.startswith(self.allowed_prefixes)
