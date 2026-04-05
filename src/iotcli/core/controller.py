"""Device controller — orchestrates protocol handlers with connection lifecycle."""

from __future__ import annotations

import concurrent.futures
from typing import Any

from iotcli.core.device import Device
from iotcli.core.registry import protocol_registry
from iotcli.core.exceptions import ConnectionError, UnknownProtocolError


class DeviceController:
    """High-level device operations that hide protocol details."""

    def __init__(self, verbose: bool = False, debug: bool = False):
        self.verbose = verbose
        self.debug = debug

    def _handler(self, device: Device):
        """Instantiate the correct protocol handler for a device."""
        cls = protocol_registry.get_or_raise(device.protocol)
        return cls(device.merge_dict(), verbose=self.verbose, debug=self.debug)

    def turn_on(self, device: Device) -> bool:
        proto = self._handler(device)
        if not proto.connect():
            raise ConnectionError(device.name)
        try:
            return proto.turn_on()
        finally:
            proto.disconnect()

    def turn_off(self, device: Device) -> bool:
        proto = self._handler(device)
        if not proto.connect():
            raise ConnectionError(device.name)
        try:
            return proto.turn_off()
        finally:
            proto.disconnect()

    def get_status(self, device: Device) -> dict[str, Any]:
        proto = self._handler(device)
        if not proto.connect():
            raise ConnectionError(device.name)
        try:
            return proto.get_status()
        finally:
            proto.disconnect()

    def set_value(self, device: Device, prop: str, value: Any) -> bool:
        proto = self._handler(device)
        if not proto.connect():
            raise ConnectionError(device.name)
        try:
            return proto.set_value(prop, value)
        finally:
            proto.disconnect()

    def test_connection(self, device: Device) -> bool:
        proto = self._handler(device)
        return proto.test_connection()

    def status_all(self, devices: dict[str, Device]) -> dict[str, dict[str, Any]]:
        """Query all devices in parallel, return {name: status_dict}."""
        results: dict[str, dict[str, Any]] = {}

        def _check(name: str, dev: Device) -> tuple[str, dict[str, Any]]:
            try:
                return name, self.get_status(dev)
            except Exception as e:
                return name, {"online": False, "error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(_check, name, dev): name for name, dev in devices.items()
            }
            for future in concurrent.futures.as_completed(futures):
                name, status = future.result()
                results[name] = status

        return results
