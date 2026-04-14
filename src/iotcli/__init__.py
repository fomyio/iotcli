"""iotcli — Universal IoT device control CLI for humans and AI agents."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("iotcli")
except PackageNotFoundError:
    __version__ = "0.0.0"
