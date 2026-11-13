"""Deferred tool discovery for the example harness."""
from __future__ import annotations


class ToolRegistry:
    def __init__(self) -> None:
        self._tools = {}
        self._deferred = []

    def register(self, name: str, handler, deferred: bool = False) -> None:
        self._tools[name] = handler
        if deferred:
            self._deferred.append(name)

    def discover_tools(self, query: str):
        return [name for name in self._deferred if query.lower() in name.lower()]

    def invoke(self, call):
        if call.name not in self._tools:
            raise KeyError(f"unknown tool: {call.name}")
        return self._tools[call.name](call.arguments)
