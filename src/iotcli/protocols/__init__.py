"""Protocol package — importing this module triggers auto-registration of all protocols."""

# Each module uses @register_protocol which adds itself to the global registry on import.
from iotcli.protocols import miio, tuya, mqtt, http, lgac  # noqa: F401

from iotcli.protocols.base import BaseProtocol, ProtocolMeta

__all__ = ["BaseProtocol", "ProtocolMeta"]
