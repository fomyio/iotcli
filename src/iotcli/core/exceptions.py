"""Custom exception hierarchy for iotcli."""


class IoTCLIError(Exception):
    """Base exception for all iotcli errors."""


class DeviceNotFoundError(IoTCLIError):
    """Raised when a device name is not found in config."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Device not found: {name}")


class ProtocolError(IoTCLIError):
    """Raised when a protocol operation fails."""

    def __init__(self, protocol: str, message: str):
        self.protocol = protocol
        super().__init__(f"[{protocol}] {message}")


class ConnectionError(IoTCLIError):
    """Raised when a device connection fails."""

    def __init__(self, device_name: str, reason: str = ""):
        self.device_name = device_name
        detail = f": {reason}" if reason else ""
        super().__init__(f"Cannot connect to {device_name}{detail}")


class CredentialError(IoTCLIError):
    """Raised when credentials are missing or invalid."""

    def __init__(self, device_name: str, field: str):
        self.device_name = device_name
        self.field = field
        super().__init__(f"Missing credential '{field}' for device {device_name}")


class UnknownProtocolError(IoTCLIError):
    """Raised when a protocol name is not in the registry."""

    def __init__(self, name: str, available: list[str] | None = None):
        self.name = name
        msg = f"Unknown protocol: {name}"
        if available:
            msg += f" (available: {', '.join(available)})"
        super().__init__(msg)
