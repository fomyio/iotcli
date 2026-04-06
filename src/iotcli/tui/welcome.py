"""Interactive welcome screen — persistent loop with animated mascot."""

from __future__ import annotations

import click
from rich.console import Console

from iotcli.config.manager import ConfigManager
from iotcli.tui.mascot import MascotMood, render_inline

console = Console()


# ── Main loop ────────────────────────────────────────────────────────────────


def run_interactive(ctx: click.Context) -> None:
    """Main interactive loop — animated welcome, menu, dispatch, repeat."""
    from iotcli.tui.interactive import AnimatedWelcome

    config: ConfigManager = ctx.obj["config"]
    first_run = True

    while True:
        # Full-screen animated welcome + menu
        screen = AnimatedWelcome(config, first_run=first_run)
        action = screen.run()
        first_run = False

        if action is None or action == "exit":
            console.print()
            console.print(render_inline(MascotMood.HAPPY, "[dim]Goodbye![/dim]"))
            console.print()
            break

        # Dispatch — everything stays in full-screen TUI
        _dispatch_action(action, ctx)


# ── Dispatch ─────────────────────────────────────────────────────────────────


def _dispatch_action(action: str, ctx: click.Context) -> None:
    """Route a menu selection — all actions stay inside full-screen TUI."""
    config: ConfigManager = ctx.obj["config"]

    if action == "help":
        _help_in_tui(ctx)

    elif action == "discover":
        _discover_in_tui(ctx)

    elif action == "status-all":
        _status_all_in_tui(ctx)

    elif action == "list":
        _list_in_tui(ctx)

    elif action == "skills":
        _skills_in_tui(ctx)

    elif action == "control":
        _control_in_tui(ctx)

    elif action == "setup":
        from iotcli.tui.wizard import SetupWizard
        wizard = SetupWizard(
            config=config,
            verbose=ctx.obj.get("verbose", False),
            debug=ctx.obj.get("debug", False),
        )
        wizard.run()

    elif action == "cloud-import":
        _cloud_import_interactive(ctx)


# ── TUI-native action handlers ──────────────────────────────────────────────


def _help_in_tui(ctx: click.Context) -> None:
    """Show CLI help text inside a TUI results viewer."""
    from iotcli.tui.interactive import TUITaskRunner

    help_text = ctx.get_help()
    lines = help_text.splitlines()

    runner = TUITaskRunner("Help", "iotcli command reference")
    runner.run(lambda r: r.show_results(lines))


def _discover_in_tui(ctx: click.Context) -> None:
    """Run network discovery inside the TUI."""
    from iotcli.tui.interactive import TUITaskRunner
    from iotcli.discovery.scanner import DiscoveryScanner, ScanConfig

    config: ConfigManager = ctx.obj["config"]

    def task(runner: TUITaskRunner) -> None:
        scanner = DiscoveryScanner(
            verbose=ctx.obj.get("verbose", False),
            debug=ctx.obj.get("debug", False),
        )
        devices = scanner.discover_sync()

        lines: list[str] = []
        if not devices:
            lines.append("No IoT devices found.")
            lines.append("")
            lines.append("Tips:")
            lines.append("  • Ensure devices are powered on and on the same network")
            lines.append("  • Try: iotcli discover --network 192.168.1.0/24")
        else:
            lines.append(f"Found {len(devices)} device(s):")
            lines.append("")
            for dev in devices:
                lines.append(f"  {dev['name']}")
                lines.append(f"      protocol : {dev['protocol']}")
                lines.append(f"      ip       : {dev['ip']}")
                lines.append(f"      status   : {dev['status']}")
                if dev.get("missing_info"):
                    lines.append(f"      missing  : {', '.join(dev['missing_info'])}")
                lines.append("")

        runner.show_results(lines)

    runner = TUITaskRunner("Network Discovery", "Scanning for IoT devices…")
    runner.run(task)


def _status_all_in_tui(ctx: click.Context) -> None:
    """Query all devices and show results inside the TUI."""
    from iotcli.tui.interactive import TUITaskRunner
    from iotcli.core.controller import DeviceController
    from iotcli.core.device import DeviceStatus

    config: ConfigManager = ctx.obj["config"]

    def task(runner: TUITaskRunner) -> None:
        devices = config.get_all_devices()
        if not devices:
            runner.show_results(["No devices configured."])
            return

        ctrl = DeviceController(
            verbose=ctx.obj.get("verbose", False),
            debug=ctx.obj.get("debug", False),
        )
        results = ctrl.status_all(devices)

        # Update config status
        for name, status in results.items():
            if status.get("online"):
                config.update_status(name, DeviceStatus.ONLINE)
            else:
                config.update_status(name, DeviceStatus.OFFLINE)

        # Format lines
        lines: list[str] = []
        for name, status in results.items():
            online = status.get("online", False)
            icon = "●" if online else "○"
            state = "online" if online else "offline"
            lines.append(f"  {icon} {name} — {state}")

            if online:
                for k, v in status.items():
                    if k in ("online", "dps"):
                        continue
                    lines.append(f"      {k}: {v}")
            elif "error" in status:
                lines.append(f"      error: {status['error']}")
            lines.append("")

        runner.show_results(lines)

    runner = TUITaskRunner("Status Check", "Querying all devices…")
    runner.run(task)


def _list_in_tui(ctx: click.Context) -> None:
    """List configured devices inside the TUI."""
    from iotcli.tui.interactive import TUITaskRunner

    config: ConfigManager = ctx.obj["config"]
    devices = config.get_all_devices()

    lines: list[str] = []
    if not devices:
        lines.append("No devices configured.")
    else:
        # Table header
        lines.append(f"  {'Name':<28} {'Protocol':<10} {'IP':<16} {'Port':<6} {'Status'}")
        lines.append(f"  {'─' * 28} {'─' * 10} {'─' * 16} {'─' * 6} {'─' * 10}")
        for name, dev in devices.items():
            st = getattr(dev, "status", None)
            status_val = st.value if st else "?"
            lines.append(
                f"  {name:<28} {dev.protocol:<10} {dev.ip:<16} {str(dev.port):<6} {status_val}"
            )
        lines.append("")
        lines.append(f"  Total: {len(devices)} device(s)")

    runner = TUITaskRunner("Configured Devices")
    runner.run(lambda r: r.show_results(lines))


def _skills_in_tui(ctx: click.Context) -> None:
    """Generate AI agent skills and show result in TUI."""
    from iotcli.tui.interactive import TUITaskRunner
    from iotcli.skills.generator import SkillGenerator

    config: ConfigManager = ctx.obj["config"]

    def task(runner: TUITaskRunner) -> None:
        gen = SkillGenerator(config)
        results = gen.generate_all()
        lines = [f"Generated {len(results)} skill file(s):", ""]
        for path in results:
            lines.append(f"  • {path}")
        runner.show_results(lines)

    runner = TUITaskRunner("AI Agent Skills", "Generating skill files…")
    runner.run(task)


# ── Control (interactive sub-flow inside TUI) ───────────────────────────────


def _control_in_tui(ctx: click.Context) -> None:
    """Interactive control sub-flow — pickers + execution all in TUI."""
    from iotcli.tui.interactive import animated_select, TUITaskRunner
    from iotcli.core.controller import DeviceController
    from iotcli.core.device import DeviceStatus

    config: ConfigManager = ctx.obj["config"]
    device_names = config.device_names()

    if not device_names:
        runner = TUITaskRunner("Control")
        runner.run(lambda r: r.show_results(["No devices configured. Run setup first."]))
        return

    # Pick device (full-screen picker)
    device_name = animated_select(
        title="Which device?",
        choices=[(name, name) for name in device_names],
        subtitle="Select a device to control",
    )
    if device_name is None:
        return

    # Pick action (full-screen picker)
    action = animated_select(
        title=f"Control: {device_name}",
        choices=[
            ("Get status", "status"),
            ("Turn ON", "on"),
            ("Turn OFF", "off"),
            ("Set a property", "set"),
        ],
        subtitle="What would you like to do?",
    )
    if action is None:
        return

    # Handle set: ask for property=value
    value = None
    if action == "set":
        value = animated_select(
            title=f"Set property on {device_name}",
            choices=[
                ("brightness=80", "brightness=80"),
                ("color_temperature=4000", "color_temperature=4000"),
                ("power=on", "power=on"),
                ("power=off", "power=off"),
                ("Enter custom value…", "__custom__"),
            ],
            subtitle="Pick a preset or enter custom",
        )
        if value is None:
            return
        if value == "__custom__":
            from InquirerPy import inquirer
            try:
                value = inquirer.text(
                    message="Property=Value (e.g. brightness=80):",
                ).execute()
            except KeyboardInterrupt:
                return
            if not value or "=" not in value:
                runner = TUITaskRunner("Control Error")
                runner.run(lambda r: r.show_results(["Invalid format. Use: property=value"]))
                return

    # Execute the command inside TUI
    def task(runner: TUITaskRunner) -> None:
        ctrl = DeviceController(
            verbose=ctx.obj.get("verbose", False),
            debug=ctx.obj.get("debug", False),
        )
        device = config.get_device(device_name)

        try:
            if action == "status":
                status = ctrl.get_status(device)
                if status.get("online"):
                    config.update_status(device_name, DeviceStatus.ONLINE)
                else:
                    config.update_status(device_name, DeviceStatus.OFFLINE)

                lines = []
                online = status.get("online", False)
                icon = "●" if online else "○"
                lines.append(f"  {icon} {device_name} — {'online' if online else 'offline'}")
                lines.append("")
                for k, v in status.items():
                    if k in ("online", "dps"):
                        continue
                    lines.append(f"    {k}: {v}")
                runner.show_results(lines)

            elif action == "on":
                ok = ctrl.turn_on(device)
                if ok:
                    config.update_status(device_name, DeviceStatus.ONLINE)
                    runner.show_results([f"  ● {device_name} is now ON"])
                else:
                    runner.show_results([f"  ✗ Failed to turn on {device_name}"])

            elif action == "off":
                ok = ctrl.turn_off(device)
                if ok:
                    config.update_status(device_name, DeviceStatus.ONLINE)
                    runner.show_results([f"  ● {device_name} is now OFF"])
                else:
                    runner.show_results([f"  ✗ Failed to turn off {device_name}"])

            elif action == "set":
                prop, raw = value.split("=", 1)
                coerced = _coerce(raw)
                ok = ctrl.set_value(device, prop, coerced)
                if ok:
                    config.update_status(device_name, DeviceStatus.ONLINE)
                    runner.show_results([f"  ✓ Set {prop} = {coerced}"])
                else:
                    runner.show_results([f"  ✗ Failed to set {prop}"])

        except Exception as e:
            runner.show_results([f"  Error: {e}"])

    labels = {"status": "Getting status…", "on": "Turning on…", "off": "Turning off…", "set": "Setting property…"}
    runner = TUITaskRunner(f"Control: {device_name}", labels.get(action, "Working…"))
    runner.run(task)


def _coerce(raw: str):
    """Type-coerce a string value."""
    low = raw.lower()
    if low in ("true", "on", "yes"):
        return True
    if low in ("false", "off", "no"):
        return False
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


# ── Cloud import ─────────────────────────────────────────────────────────────


def _cloud_import_interactive(ctx: click.Context) -> None:
    """Import devices from a cloud account (Tuya, Xiaomi)."""
    config: ConfigManager = ctx.obj["config"]
    _cloud_import_with_config(config)


def _cloud_import_with_config(config: ConfigManager) -> str | None:
    """Cloud import provider picker — works from both main menu and wizard."""
    from iotcli.tui.interactive import animated_select

    # Check which accounts are saved
    has_tuya = bool(config.vault.load("__tuya_cloud__").get("api_key"))
    has_xiaomi = bool(config.vault.load("__xiaomi_cloud__").get("username"))

    choices = [
        ("Tuya / Smart Life", "tuya"),
        ("Xiaomi / Mi Home", "xiaomi"),
    ]
    if has_tuya or has_xiaomi:
        choices.append(("Manage saved accounts", "manage"))

    provider = animated_select(
        title="Import devices from cloud",
        choices=choices,
        subtitle="Select your cloud platform",
    )
    if provider is None:
        return "__back__"

    if provider == "tuya":
        return _tuya_import(config)
    if provider == "xiaomi":
        return _xiaomi_import(config)
    if provider == "manage":
        return _manage_cloud_accounts(config)

    return None


def _manage_cloud_accounts(config: ConfigManager) -> str | None:
    """View and delete saved cloud accounts."""
    from iotcli.tui.interactive import animated_select
    from iotcli.tui import prompts
    from iotcli.cloud.tuya_cloud import TUYA_REGIONS
    from iotcli.cloud.xiaomi_cloud import XIAOMI_REGIONS

    tuya_creds = config.vault.load("__tuya_cloud__")
    xiaomi_creds = config.vault.load("__xiaomi_cloud__")

    choices = []
    if tuya_creds.get("api_key"):
        region = TUYA_REGIONS.get(tuya_creds.get("region", ""), tuya_creds.get("region", "?"))
        choices.append((f"Remove Tuya account (API Key: {tuya_creds['api_key'][:6]}…, region: {region})", "tuya"))
    if xiaomi_creds.get("username"):
        user = xiaomi_creds["username"]
        masked = user[:3] + "…" + user[-4:] if len(user) > 7 else user[:3] + "…"
        region = XIAOMI_REGIONS.get(xiaomi_creds.get("region", ""), xiaomi_creds.get("region", "?"))
        choices.append((f"Remove Xiaomi account ({masked}, region: {region})", "xiaomi"))

    if not choices:
        prompts.info("No saved cloud accounts.")
        return None

    pick = animated_select(
        title="Manage Cloud Accounts",
        choices=choices,
        subtitle="Select an account to remove",
    )
    if pick is None:
        return "__back__"

    if pick == "tuya":
        config.vault.delete("__tuya_cloud__")
        prompts.success("Tuya cloud account removed.", with_mascot=True)
    elif pick == "xiaomi":
        config.vault.delete("__xiaomi_cloud__")
        prompts.success("Xiaomi cloud account removed.", with_mascot=True)

    return None


def _tuya_import(config: ConfigManager) -> str | None:
    """Full Tuya cloud import flow."""
    from iotcli.tui.interactive import animated_select
    from iotcli.tui import prompts
    from iotcli.cloud.tuya_cloud import (
        TUYA_REGIONS, SETUP_STEPS, fetch_devices, scan_local_ips, guess_profile,
    )
    from iotcli.core.device import slugify

    # Check for saved cloud account
    saved = config.vault.load("__tuya_cloud__")
    api_key = saved.get("api_key", "")
    api_secret = saved.get("api_secret", "")
    region = saved.get("region", "")

    if api_key and api_secret and region:
        region_label = TUYA_REGIONS.get(region, region)
        use_saved = animated_select(
            title="Tuya Cloud Account",
            choices=[
                (f"Use saved account (API Key: {api_key[:6]}…, region: {region_label})", "saved"),
                ("Enter new credentials", "new"),
            ],
            subtitle="A saved Tuya account was found",
        )
        if use_saved is None:
            return "__back__"
        if use_saved == "saved":
            # Skip credential prompts, go straight to fetch
            pass
        else:
            api_key = api_secret = region = ""

    if not (api_key and api_secret):
        # Show setup instructions
        console.print()
        from rich.panel import Panel
        console.print(Panel(
            SETUP_STEPS,
            title="[bold cyan]Tuya IoT Platform Setup[/bold cyan]",
            subtitle="[dim]iot.tuya.com[/dim]",
            border_style="cyan",
            expand=False,
            padding=(1, 2),
        ))
        console.print()

        # Get credentials
        try:
            api_key = prompts.text("API Key (Access ID)")
        except KeyboardInterrupt:
            return "__back__"
        if not api_key:
            return "__back__"

        try:
            api_secret = prompts.secret("API Secret (Access Secret)")
        except KeyboardInterrupt:
            return "__back__"
        if not api_secret:
            return "__back__"

    if not region:
        region = animated_select(
            title="Select your region",
            choices=[(f"{code}  —  {name}", code) for code, name in TUYA_REGIONS.items()],
            subtitle="This must match your Tuya IoT Platform project",
        )
        if region is None:
            return "__back__"

    # Fetch devices from cloud
    console.print()
    with console.status("[bold blue]Connecting to Tuya Cloud...", spinner="dots"):
        devices, error = fetch_devices(api_key, api_secret, region)

    if error:
        prompts.error(error, with_mascot=True)
        return None

    if not devices:
        prompts.warn("No devices found in your Tuya account.")
        return None

    prompts.success(f"Found {len(devices)} device(s) in your Tuya account!", with_mascot=True)

    # Try to find local IPs
    console.print()
    with console.status("[bold blue]Scanning local network for device IPs...", spinner="dots"):
        devices = scan_local_ips(devices)

    # Show devices and let user pick which to import
    ip_found = sum(1 for d in devices if d.ip)
    if ip_found:
        prompts.success(f"Found local IPs for {ip_found}/{len(devices)} device(s).")
    else:
        prompts.info("No local IPs found — you can set them manually later.")

    console.print()

    # Build choices
    dev_choices = []
    for d in devices:
        status = "[green]online[/green]" if d.online else "[dim]offline[/dim]"
        ip_str = d.ip if d.ip else "no IP"
        label = f"{d.name}  ({d.category})  [{ip_str}]"
        dev_choices.append((label, d.device_id))
    dev_choices.append(("Import ALL devices", "__all__"))

    pick = animated_select(
        title=f"Found {len(devices)} Tuya devices",
        choices=dev_choices,
        subtitle="Select which device(s) to import",
    )
    if pick is None:
        return "__back__"

    # Import selected device(s)
    to_import = devices if pick == "__all__" else [d for d in devices if d.device_id == pick]

    imported = 0
    for dev in to_import:
        name = slugify(dev.name)
        ip = dev.ip or "0.0.0.0"

        # Ask for IP if not found
        if not dev.ip:
            console.print(f"\n  [bold]{dev.name}[/bold] — no local IP found.")
            ip = prompts.text(f"IP for {dev.name}", default="0.0.0.0")

        profile = guess_profile(dev.category)
        device_dict = {
            "name": name,
            "protocol": "tuya",
            "ip": ip,
            "port": 6668,
            "device_id": dev.device_id,
            "local_key": dev.local_key,
            "version": "3.4",
            "profile": profile,
            "status": "configured",
        }

        config.add_device(device_dict)
        prompts.success(f"Imported: {name} (profile: {profile})", with_mascot=True)
        imported += 1

    console.print()
    prompts.success(f"Done! Imported {imported} device(s).", with_mascot=True)

    # Vault the cloud credentials for future use
    config.vault.save("__tuya_cloud__", {
        "api_key": api_key,
        "api_secret": api_secret,
        "region": region,
    })
    prompts.info("Cloud credentials saved (encrypted) for future imports.")

    return None


# ── Xiaomi Cloud import ──────────────────────────────────────────────────────


def _xiaomi_import(config: ConfigManager) -> str | None:
    """Full Xiaomi Cloud import flow — username/password with captcha + 2FA."""
    from iotcli.tui.interactive import animated_select
    from iotcli.tui import prompts
    from iotcli.cloud.xiaomi_cloud import (
        XIAOMI_REGIONS, SETUP_STEPS, fetch_devices,
    )
    from iotcli.core.device import slugify

    # Check for saved cloud account
    saved = config.vault.load("__xiaomi_cloud__")
    username = saved.get("username", "")
    password = saved.get("password", "")
    region = saved.get("region", "")

    if username and password and region:
        masked_user = username[:3] + "…" + username[-4:] if len(username) > 7 else username[:3] + "…"
        region_label = XIAOMI_REGIONS.get(region, region)
        use_saved = animated_select(
            title="Xiaomi Cloud Account",
            choices=[
                (f"Use saved account ({masked_user}, region: {region_label})", "saved"),
                ("Enter new credentials", "new"),
            ],
            subtitle="A saved Xiaomi account was found",
        )
        if use_saved is None:
            return "__back__"
        if use_saved == "saved":
            pass
        else:
            username = password = region = ""

    if not (username and password):
        # Show setup instructions
        console.print()
        from rich.panel import Panel
        console.print(Panel(
            SETUP_STEPS,
            title="[bold cyan]Xiaomi / Mi Home Import[/bold cyan]",
            subtitle="[dim]Mi Home app credentials[/dim]",
            border_style="cyan",
            expand=False,
            padding=(1, 2),
        ))
        console.print()

        # Get credentials
        try:
            username = prompts.text("Mi Home username (email/phone)")
        except KeyboardInterrupt:
            return "__back__"
        if not username:
            return "__back__"
        try:
            password = prompts.secret("Mi Home password")
        except KeyboardInterrupt:
            return "__back__"
        if not password:
            return "__back__"

    if not region:
        region = animated_select(
            title="Select your region",
            choices=[(f"{code}  —  {name}", code) for code, name in XIAOMI_REGIONS.items()],
            subtitle="This should match your Mi Home app region",
        )
        if region is None:
            return "__back__"

    # Captcha callback: show image path, ask for code
    def on_captcha(image_path: str) -> str:
        prompts.warn("Captcha required!")
        prompts.info(f"Captcha image saved to: {image_path}")
        prompts.info("Open that file to see the captcha.")
        return prompts.text("Enter captcha code (case-sensitive)")

    # 2FA callback: Xiaomi sends a code to your email
    def on_2fa() -> str:
        console.print()
        prompts.warn("Two-factor authentication required!")
        prompts.info("Xiaomi sent a verification code to your email.")
        prompts.info("Check your inbox and paste the code below.")
        console.print()
        return prompts.text("Enter 2FA code from email")

    # Fetch devices — no spinner so prompts can work
    # Scan all regions with one login to find devices everywhere
    console.print()
    prompts.info("Connecting to Xiaomi Cloud...")
    devices, error = fetch_devices(
        username, password, region,
        on_captcha=on_captcha, on_2fa=on_2fa,
        scan_all_regions=True,
    )

    if error:
        prompts.error(error, with_mascot=True)
        return None

    if not devices:
        prompts.warn("No devices with usable tokens found.")
        prompts.info("Check that devices are in your Mi Home app.")
        return None

    prompts.success(f"Found {len(devices)} device(s) with tokens!", with_mascot=True)
    console.print()

    # Build choices
    dev_choices = []
    for d in devices:
        ip_str = d.ip if d.ip else "no IP"
        label = f"{d.name}  ({d.model})  [{ip_str}]"
        dev_choices.append((label, d.device_id))
    dev_choices.append(("Import ALL devices", "__all__"))

    pick = animated_select(
        title=f"Found {len(devices)} Xiaomi devices",
        choices=dev_choices,
        subtitle="Select which device(s) to import",
    )
    if pick is None:
        return "__back__"

    # Import selected device(s)
    to_import = devices if pick == "__all__" else [d for d in devices if d.device_id == pick]

    imported = 0
    for dev in to_import:
        name = slugify(dev.name)
        ip = dev.ip or "0.0.0.0"

        if not dev.ip:
            console.print(f"\n  [bold]{dev.name}[/bold] — no local IP found.")
            ip = prompts.text(f"IP for {dev.name}", default="0.0.0.0")

        device_dict = {
            "name": name,
            "protocol": "miio",
            "ip": ip,
            "port": 54321,
            "device_id": dev.device_id,
            "token": dev.token,
            "status": "configured",
        }

        config.add_device(device_dict)
        prompts.success(f"Imported: {name} (model: {dev.model})", with_mascot=True)
        imported += 1

    console.print()
    prompts.success(f"Done! Imported {imported} device(s).", with_mascot=True)

    # Vault the cloud credentials for future use
    config.vault.save("__xiaomi_cloud__", {
        "username": username,
        "password": password,
        "region": region,
    })
    prompts.info("Cloud credentials saved (encrypted) for future imports.")

    return None
