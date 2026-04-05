"""Tuya Cloud importer — pull all devices + local keys from Tuya IoT Platform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TUYA_REGIONS = {
    "eu": "Europe (Central)",
    "eu-w": "Europe (West)",
    "us": "US (East)",
    "us-e": "US (West)",
    "cn": "China",
    "in": "India",
}

SETUP_URL = "https://iot.tuya.com"

SETUP_STEPS = """\
1. Go to [bold]iot.tuya.com[/bold] → create a free account
2. Create a Cloud Project (any name)
3. Under [bold]Devices[/bold] → Link your Tuya / Smart Life app
4. Go to [bold]Cloud → API Credentials[/bold]
5. Copy the [bold]Access ID[/bold] (API Key) and [bold]Access Secret[/bold]
6. Note your region (EU, US, etc.)"""


@dataclass
class TuyaCloudDevice:
    """A device returned from the Tuya Cloud API."""
    name: str
    device_id: str
    local_key: str
    mac: str
    category: str
    product_name: str
    online: bool
    ip: str  # filled by local scan, empty string if not found


def fetch_devices(
    api_key: str,
    api_secret: str,
    region: str = "eu",
    device_id: str = "",
) -> tuple[list[TuyaCloudDevice], str | None]:
    """Pull all devices from Tuya Cloud.

    Returns:
        (devices, error_message) — devices is empty list on failure.
    """
    try:
        import tinytuya
    except ImportError:
        return [], "tinytuya is not installed. Run: pip install tinytuya"

    try:
        cloud = tinytuya.Cloud(
            apiRegion=region,
            apiKey=api_key,
            apiSecret=api_secret,
            apiDeviceID=device_id or "",
        )

        raw = cloud.getdevices(verbose=False)

        if not raw:
            return [], "No devices found. Make sure your Tuya/Smart Life app is linked to the IoT Platform project."

        if isinstance(raw, dict) and raw.get("Error"):
            payload = raw.get("Payload", "")
            err_code = raw.get("Err", "")
            msg = f"Tuya API error: {payload or raw['Error']}"
            # Add guidance for common error codes
            if "1106" in str(payload):
                msg += (
                    "\n\n  → Go to iot.tuya.com → your project → Service API"
                    "\n  → Subscribe to: 'IoT Core' and 'Smart Home Device Management'"
                    "\n  → Then try again."
                )
            elif "1100" in str(payload) or "sign" in str(payload).lower():
                msg += "\n\n  → Check your API Key and API Secret are correct."
            elif "2406" in str(payload):
                msg += "\n\n  → Your API calls exceeded the rate limit. Wait a moment and try again."
            return [], msg

        devices: list[TuyaCloudDevice] = []
        for d in raw:
            devices.append(TuyaCloudDevice(
                name=d.get("name", "Unknown"),
                device_id=d.get("id", ""),
                local_key=d.get("key", ""),
                mac=d.get("mac", ""),
                category=d.get("category", ""),
                product_name=d.get("product_name", d.get("product_id", "")),
                online=d.get("online", False),
                ip="",  # to be filled by local scan
            ))

        return devices, None

    except Exception as e:
        return [], f"Failed to connect to Tuya Cloud: {e}"


def scan_local_ips(devices: list[TuyaCloudDevice]) -> list[TuyaCloudDevice]:
    """Try to find local IPs for cloud devices by scanning the network."""
    try:
        import tinytuya
        scan = tinytuya.deviceScan(verbose=False, maxretry=2)
        # scan returns {ip: {gwId, ...}, ...}
        id_to_ip: dict[str, str] = {}
        if isinstance(scan, dict):
            for ip, info in scan.items():
                gw_id = info.get("gwId", "")
                if gw_id:
                    id_to_ip[gw_id] = ip

        for dev in devices:
            if dev.device_id in id_to_ip:
                dev.ip = id_to_ip[dev.device_id]

    except Exception:
        pass  # local scan is best-effort

    return devices


def guess_profile(category: str) -> str:
    """Map Tuya device category to a profile name."""
    category_map = {
        "dj": "light",      # Light
        "dd": "light",      # Light strip
        "fwd": "light",     # Ambient light
        "dc": "light",      # String lights
        "kg": "switch",     # Switch
        "cz": "switch",     # Socket/Plug
        "pc": "switch",     # Power strip
        "cwwsq": "petfeeder",  # Pet feeder
    }
    return category_map.get(category, "generic")
