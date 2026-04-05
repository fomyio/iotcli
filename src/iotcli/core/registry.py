"""Protocol registry — protocols self-register via decorator, looked up by name."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iotcli.protocols.base import BaseProtocol


class _ProtocolRegistry:
    """Singleton registry mapping protocol names to their handler classes."""

    def __init__(self) -> None:
        self._protocols: dict[str, type[BaseProtocol]] = {}

    def register(
        self,
        name: str,
        cls: type[BaseProtocol],
        aliases: list[str] | None = None,
    ) -> None:
        self._protocols[name] = cls
        for alias in aliases or []:
            self._protocols[alias] = cls

    def get(self, name: str) -> type[BaseProtocol] | None:
        return self._protocols.get(name)

    def get_or_raise(self, name: str) -> type[BaseProtocol]:
        from iotcli.core.exceptions import UnknownProtocolError

        cls = self._protocols.get(name)
        if cls is None:
            raise UnknownProtocolError(name, available=self.names())
        return cls

    def names(self) -> list[str]:
        """Return canonical protocol names (no aliases)."""
        seen: dict[int, str] = {}
        for name, cls in self._protocols.items():
            cid = id(cls)
            if cid not in seen:
                seen[cid] = name
        return sorted(seen.values())

    def all(self) -> dict[str, type[BaseProtocol]]:
        """Return {canonical_name: cls} without aliases."""
        seen: dict[int, tuple[str, type[BaseProtocol]]] = {}
        for name, cls in self._protocols.items():
            cid = id(cls)
            if cid not in seen:
                seen[cid] = (name, cls)
        return {n: c for n, c in seen.values()}

    def __contains__(self, name: str) -> bool:
        return name in self._protocols


protocol_registry = _ProtocolRegistry()


def register_protocol(name: str, *, aliases: list[str] | None = None):
    """Class decorator that registers a protocol handler.

    Usage:
        @register_protocol("tuya", aliases=["petfeeder"])
        class TuyaProtocol(BaseProtocol): ...
    """

    def decorator(cls: type[BaseProtocol]) -> type[BaseProtocol]:
        protocol_registry.register(name, cls, aliases=aliases)
        return cls

    return decorator
