"""
src/upcasting/registry.py
==========================
UpcasterRegistry — chains upcasters automatically.

Upcasters are pure synchronous functions that transform old event
payloads to the current schema on read. They NEVER write to the database.
"""
from __future__ import annotations


class UpcasterRegistry:
    """
    Registry that chains upcasters automatically.

    Usage:
        registry = UpcasterRegistry()

        @registry.upcaster("CreditAnalysisCompleted", from_version=1, to_version=2)
        def upcast_credit_v1_v2(payload: dict) -> dict:
            payload = dict(payload)
            payload.setdefault("model_versions", {})
            return payload

        event = registry.upcast(event)
    """

    def __init__(self):
        # {event_type: {from_version: upcaster_fn}}
        self._upcasters: dict[str, dict[int, callable]] = {}

    def upcaster(self, event_type: str, from_version: int, to_version: int):
        """Decorator to register an upcaster function."""
        def decorator(fn):
            self._upcasters.setdefault(event_type, {})[from_version] = fn
            return fn
        return decorator

    def register(self, event_type: str, from_version: int, fn: callable) -> None:
        """Register an upcaster function directly (non-decorator form)."""
        self._upcasters.setdefault(event_type, {})[from_version] = fn

    def upcast(self, event: dict) -> dict:
        """
        Apply chain of upcasters until latest version reached.
        Copies event dict — never mutates the original.
        """
        et = event.get("event_type")
        v = event.get("event_version", 1)
        chain = self._upcasters.get(et, {})

        while v in chain:
            event = dict(event)
            event["payload"] = chain[v](dict(event.get("payload", {})))
            v += 1
            event["event_version"] = v

        return event

    def registered_types(self) -> list[str]:
        """List all event types that have upcasters."""
        return list(self._upcasters.keys())