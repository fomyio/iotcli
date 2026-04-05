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

        # Dispatch the action (outside full-screen, normal terminal output)
        result = _dispatch_action(action, ctx)

        # If sub-menu returned "back", skip the pause and loop immediately
        if result == "__back__":
            continue

        # Pause before returning to welcome screen
        console.print()
        _wait_for_enter()


def _wait_for_enter() -> None:
    """Simple inline pause so user can read output before full-screen returns."""
    console.print()
    try:
        input("  Press Enter to return to menu...")
    except (KeyboardInterrupt, EOFError):
        pass


# ── Dispatch ─────────────────────────────────────────────────────────────────


def _dispatch_action(action: str, ctx: click.Context) -> str | None:
    """Route a menu selection. Returns '__back__' if user went back."""
    config: ConfigManager = ctx.obj["config"]

    if action == "help":
        click.echo(ctx.get_help())
        return None

    if action == "discover":
        from iotcli.cli.commands.discover import discover
        ctx.invoke(discover)
        return None

    if action == "status-all":
        from iotcli.cli.commands.device import status_all
        ctx.invoke(status_all)
        return None

    if action == "setup":
        from iotcli.tui.wizard import SetupWizard
        wizard = SetupWizard(
            config=config,
            verbose=ctx.obj.get("verbose", False),
            debug=ctx.obj.get("debug", False),
        )
        result = wizard.run()
        return result  # "__back__" if user cancelled, None otherwise

    if action == "list":
        from iotcli.cli.commands.device import list_devices
        ctx.invoke(list_devices)
        return None

    if action == "skills":
        from iotcli.skills.generator import SkillGenerator
        gen = SkillGenerator(config)
        results = gen.generate_all()
        from iotcli.tui.prompts import success
        success(f"Generated {len(results)} skill file(s).", with_mascot=True)
        return None

    if action == "control":
        return _control_interactive(ctx)

    if action == "cloud-import":
        return _cloud_import_interactive(ctx)

    return None


def _control_interactive(ctx: click.Context) -> str | None:
    """Interactive control sub-flow using full-screen pickers."""
    from iotcli.tui.interactive import animated_select

    config: ConfigManager = ctx.obj["config"]
    device_names = config.device_names()

    if not device_names:
        from iotcli.tui.prompts import warn
        warn("No devices configured. Run setup first.")
        return None

    # Pick device (full-screen, animated)
    device_name = animated_select(
        title="Which device?",
        choices=[(name, name) for name in device_names],
        subtitle="Select a device to control",
    )
    if device_name is None:
        return "__back__"

    # Pick action (full-screen, animated)
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
        return "__back__"

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
                ("Enter custom value...", "__custom__"),
            ],
            subtitle="Pick a preset or enter custom",
        )
        if value is None:
            return "__back__"
        if value == "__custom__":
            from InquirerPy import inquirer
            try:
                value = inquirer.text(
                    message="Property=Value (e.g. brightness=80):",
                ).execute()
            except KeyboardInterrupt:
                return "__back__"
            if not value or "=" not in value:
                from iotcli.tui.prompts import error
                error("Invalid format. Use: property=value")
                return None

    # Execute the command (outputs to terminal normally)
    console.print()
    from iotcli.cli.commands.control import control
    ctx.invoke(control, action=action, device_name=device_name, value=value)
    return None


# ── Cloud import ─────────────────────────────────────────────────────────────


def _cloud_import_interactive(ctx: click.Context) -> str | None:
    """Import devices from a cloud account (Tuya, Xiaomi)."""
    config: ConfigManager = ctx.obj["config"]
    return _cloud_import_with_config(config)


def _cloud_import_with_config(config: ConfigManager) -> str | None:
    """Cloud import provider picker — works from both main menu and wizard."""
    from iotcli.tui.interactive import animated_select

    provider = animated_select(
        title="Import devices from cloud",
        choices=[
            ("Tuya / Smart Life", "tuya"),
            ("Xiaomi / Mi Home", "xiaomi"),
        ],
        subtitle="Select your cloud platform",
    )
    if provider is None:
        return "__back__"

    if provider == "tuya":
        return _tuya_import(config)
    if provider == "xiaomi":
        return _xiaomi_import(config)

    return None


def _tuya_import(config: ConfigManager) -> str | None:
    """Full Tuya cloud import flow."""
    from iotcli.tui.interactive import animated_select
    from iotcli.tui import prompts
    from iotcli.cloud.tuya_cloud import (
        TUYA_REGIONS, SETUP_STEPS, fetch_devices, scan_local_ips, guess_profile,
    )
    from iotcli.core.device import slugify

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
    api_key = prompts.text("API Key (Access ID)")
    if not api_key:
        return "__back__"

    api_secret = prompts.secret("API Secret (Access Secret)")
    if not api_secret:
        return "__back__"

    # Pick region
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
    username = prompts.text("Mi Home username (email/phone)")
    if not username:
        return "__back__"
    password = prompts.secret("Mi Home password")
    if not password:
        return "__back__"

    # Pick region
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

    return None
