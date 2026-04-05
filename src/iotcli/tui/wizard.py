"""Interactive TUI setup wizard — rich multi-step flow."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from iotcli.config.manager import ConfigManager
from iotcli.core.device import Device, DeviceStatus
from iotcli.core.registry import protocol_registry
from iotcli.core.controller import DeviceController
from iotcli.discovery.scanner import DiscoveryScanner, ScanConfig
from iotcli.tui import prompts
from iotcli.tui.panels import DiscoveryLive

console = Console()


def _animated_select(title, choices, subtitle=""):
    """Wrapper to use animated picker for all wizard selections."""
    from iotcli.tui.interactive import animated_select
    return animated_select(title, choices, subtitle)


class SetupWizard:
    """Multi-step interactive wizard for configuring IoT devices."""

    def __init__(
        self,
        config: ConfigManager,
        verbose: bool = False,
        debug: bool = False,
    ):
        self.config = config
        self.verbose = verbose
        self.debug = debug
        self.controller = DeviceController(verbose=verbose, debug=debug)

    # -- entry point ----------------------------------------------------------

    def run(self) -> str | None:
        """Main wizard menu. Returns '__back__' if user cancels."""
        action = _animated_select(
            "iotcli Setup Wizard",
            [
                ("Discover devices on the network", "discover"),
                ("Import devices from cloud", "cloud-import"),
                ("Add a device manually", "manual"),
                ("Reconfigure an existing device", "reconfig"),
            ],
            subtitle="Configure your IoT devices",
        )

        if action is None:
            return "__back__"
        if action == "discover":
            self._discover_flow()
        elif action == "cloud-import":
            from iotcli.tui.welcome import _cloud_import_with_config
            result = _cloud_import_with_config(self.config)
            if result == "__back__":
                return "__back__"
        elif action == "manual":
            self._manual_flow()
        elif action == "reconfig":
            self._reconfig_flow()
        return None

    # -- discover flow --------------------------------------------------------

    def _discover_flow(self) -> None:
        prompts.header("Network Discovery", "Scanning for IoT devices on your local network")

        live = DiscoveryLive()
        scanner = DiscoveryScanner(
            verbose=self.verbose,
            debug=self.debug,
            on_progress=live.on_progress,
            on_device_found=live.on_device_found,
        )

        live.start()
        try:
            devices = scanner.discover_sync()
        finally:
            live.stop()

        if not devices:
            prompts.warn("No devices found.")
            prompts.info("Make sure devices are powered on and on the same network.")
            return

        console.print()
        prompts.device_table(devices, title="Discovered Devices")

        # Let user pick which to configure
        choices = [
            (f"{d['name']} ({d['protocol']} @ {d['ip']})", str(i))
            for i, d in enumerate(devices)
        ]
        choices.append(("Configure all", "all"))

        pick = _animated_select("Which device to configure?", choices,
                                subtitle=f"Found {len(devices)} device(s)")

        if pick is None:
            return
        if pick == "all":
            for d in devices:
                self._setup_discovered(d)
        else:
            self._setup_discovered(devices[int(pick)])

    def _setup_discovered(self, raw: dict[str, Any]) -> None:
        """Configure a discovered device — ask for missing info."""
        protocol = raw.get("protocol", "")
        name = raw.get("name", "device")

        prompts.header(f"Setup: {name}", f"Protocol: {protocol}")

        # Get protocol meta for setup guide
        cls = protocol_registry.get(protocol)
        if cls and hasattr(cls, "meta"):
            meta = cls.meta
            if meta.setup_guide and raw.get("missing_info"):
                prompts.info("How to get credentials:")
                console.print(f"  [dim]{meta.setup_guide}[/dim]\n")

        # Friendly name
        friendly = prompts.text("Device name", default=name)

        # Collect missing credentials
        creds: dict[str, str] = {}
        for field in raw.get("missing_info", []):
            if field in ("token", "local_key", "pat_token", "access_token", "password"):
                val = prompts.secret(f"Enter {field}")
            else:
                val = prompts.text(f"Enter {field}")
            if val:
                creds[field] = val

        # Build device config
        device_dict: dict[str, Any] = {
            "name": friendly,
            "protocol": protocol,
            "ip": raw.get("ip", "0.0.0.0"),
            "port": raw.get("port", 0),
            "status": "configured",
        }
        if raw.get("device_id"):
            device_dict["device_id"] = str(raw["device_id"])
        if raw.get("device_type"):
            device_dict["device_type"] = raw["device_type"]
        device_dict.update(creds)

        self._test_and_save(device_dict, friendly)

    # -- manual flow ----------------------------------------------------------

    def _manual_flow(self) -> None:
        # Protocol selection
        proto_names = protocol_registry.names()
        proto_choices = []
        for pn in proto_names:
            cls = protocol_registry.get(pn)
            desc = cls.meta.display_name if cls and hasattr(cls, "meta") else pn
            proto_choices.append((f"{pn}  —  {desc}", pn))

        protocol = _animated_select("Select protocol", proto_choices,
                                    subtitle="Manual Device Setup")
        if protocol is None:
            return

        cls = protocol_registry.get_or_raise(protocol)
        meta = cls.meta

        # Show setup guide
        if meta.setup_guide:
            prompts.info("Setup guide:")
            console.print(f"  [dim]{meta.setup_guide}[/dim]\n")

        # Basic info (text inputs stay as InquirerPy — need free-form input)
        name = self._require("Device name (unique)")
        ip = self._require("IP address", default="0.0.0.0" if meta.is_cloud else "")
        port = prompts.number("Port", default=meta.default_port)

        device_dict: dict[str, Any] = {
            "name": name,
            "protocol": protocol,
            "ip": ip,
            "port": port,
            "status": "configured",
        }

        # Protocol-specific fields
        if protocol in ("tuya", "petfeeder"):
            device_dict["device_id"] = self._require("Device ID")
            device_dict["local_key"] = self._require_secret("Local Key")
            ver = prompts.text("Protocol version", default="3.4" if protocol == "petfeeder" else "3.3")
            device_dict["version"] = ver
            if protocol == "tuya":
                from iotcli.protocols.tuya import TUYA_PROFILES
                profile_choices = [
                    (f"{k}  —  {v().description}", k)
                    for k, v in TUYA_PROFILES.items()
                ]
                profile = _animated_select("Device profile", profile_choices,
                                           subtitle=f"Protocol: {protocol}")
                if profile is None:
                    return
                device_dict["profile"] = profile
            else:
                device_dict["profile"] = "petfeeder"

        elif protocol == "miio":
            device_dict["token"] = self._require_secret("32-char hex token")

        elif protocol == "mqtt":
            device_dict["device_id"] = prompts.text("Device ID (zigbee friendly name)")
            device_dict["topic_prefix"] = prompts.text("Topic prefix", default="zigbee2mqtt")
            if prompts.confirm("Broker requires authentication?", default=False):
                device_dict["username"] = prompts.text("Username")
                device_dict["password"] = prompts.secret("Password")

        elif protocol == "http":
            dt = _animated_select(
                "Device type",
                [
                    ("ESPHome", "esphome"),
                    ("Tasmota", "tasmota"),
                    ("Generic HTTP", "generic"),
                ],
                subtitle="Select the device firmware type",
            )
            if dt is None:
                return
            device_dict["device_type"] = dt

        elif protocol == "lgac":
            device_dict["device_id"] = self._require("Device ID (from connect-pat.lgthinq.com)")
            device_dict["pat_token"] = self._require_secret("PAT Token")
            device_dict["country"] = prompts.text("Country code (GB/US/DE/...)", default="GB").upper()

        self._test_and_save(device_dict, name)

    # -- reconfig flow --------------------------------------------------------

    def _reconfig_flow(self) -> None:
        names = self.config.device_names()
        if not names:
            prompts.warn("No devices configured yet.")
            return

        name = _animated_select(
            "Reconfigure Device",
            [(n, n) for n in names],
            subtitle="Select device to reconfigure",
        )
        if name is None:
            return

        device = self.config.get_device(name)

        prompts.info(f"Protocol: {device.protocol} | IP: {device.ip}")

        cls = protocol_registry.get(device.protocol)
        if cls and hasattr(cls, "meta"):
            for cred in cls.meta.required_credentials:
                if prompts.confirm(f"Update {cred}?", default=False):
                    val = prompts.secret(f"New {cred}")
                    device.credentials[cred] = val

        new_ip = prompts.text("IP address", default=device.ip)
        device_dict = device.merge_dict()
        device_dict["ip"] = new_ip

        self._test_and_save(device_dict, name)

    # -- shared helpers -------------------------------------------------------

    def _require(self, label: str, default: str = "") -> str:
        """Prompt for a non-empty text value, re-asking until filled."""
        while True:
            val = prompts.text(label, default=default).strip()
            if val:
                return val
            prompts.error(f"{label} cannot be empty.")

    def _require_secret(self, label: str) -> str:
        """Prompt for a non-empty secret value, re-asking until filled."""
        while True:
            val = prompts.secret(label).strip()
            if val:
                return val
            prompts.error(f"{label} cannot be empty.")

    def _test_and_save(self, device_dict: dict[str, Any], name: str) -> None:
        """Test connection — only save if it passes."""
        from iotcli.config.credentials import SENSITIVE_FIELDS

        creds = {k: device_dict[k] for k in SENSITIVE_FIELDS if device_dict.get(k)}

        with console.status("[bold blue]Testing connection...", spinner="dots"):
            try:
                device = Device.from_config(device_dict, credentials=creds)
                ok = self.controller.test_connection(device)
            except Exception as e:
                ok = False
                prompts.error(f"Connection error: {e}")

        if ok:
            prompts.success("Connection successful!", with_mascot=True)
            self.config.add_device(device_dict)
            from iotcli.core.device import slugify
            prompts.success(f"Device '{slugify(name)}' saved.", with_mascot=True)
        else:
            prompts.error("Connection failed — device was NOT saved.", with_mascot=True)
            prompts.info("Fix the credentials or network and try again.")
