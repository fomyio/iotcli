"""Higher-level TUI panels — discovery live view, config summary, etc."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.table import Table

console = Console()


class DiscoveryLive:
    """Live-updating display during network discovery."""

    def __init__(self) -> None:
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        )
        self._tasks: dict[str, TaskID] = {}
        self._devices: list[dict[str, Any]] = []
        self._live: Live | None = None

    def start(self) -> None:
        self._live = Live(self._build_layout(), console=console, refresh_per_second=8)
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()

    def on_progress(self, protocol: str, current: int, total: int) -> None:
        if protocol not in self._tasks:
            self._tasks[protocol] = self.progress.add_task(protocol, total=total)
        self.progress.update(self._tasks[protocol], completed=current)
        if self._live:
            self._live.update(self._build_layout())

    def on_device_found(self, device: dict[str, Any]) -> None:
        self._devices.append(device)
        if self._live:
            self._live.update(self._build_layout())

    def _build_layout(self):
        from rich.layout import Layout
        from rich.text import Text

        layout = Layout()
        layout.split_column(
            Layout(Panel(self.progress, title="Scanning", border_style="blue"), size=8),
            Layout(self._device_list(), minimum_size=3),
        )
        return layout

    def _device_list(self):
        if not self._devices:
            return Panel("[dim]Waiting for devices...[/dim]", title="Found", border_style="dim")
        table = Table(show_header=True, border_style="green", expand=True)
        table.add_column("Name", style="bold")
        table.add_column("Protocol", style="cyan")
        table.add_column("IP")
        for d in self._devices:
            table.add_row(d.get("name", "?"), d.get("protocol", "?"), d.get("ip", "?"))
        return Panel(table, title=f"Found ({len(self._devices)})", border_style="green")


def config_summary(devices: dict[str, Any]) -> None:
    """Print a summary table of all configured devices."""
    table = Table(title="Configured Devices", border_style="blue", show_lines=True)
    table.add_column("Name", style="bold")
    table.add_column("Protocol", style="cyan")
    table.add_column("IP")
    table.add_column("Port", justify="right")
    table.add_column("Status")
    table.add_column("Credentials", justify="center")

    for name, dev in devices.items():
        has_creds = bool(dev.credentials) if hasattr(dev, "credentials") else False
        cred_icon = "[green]yes[/green]" if has_creds else "[red]no[/red]"
        st = getattr(dev, "status", None)
        status_val = st.value if st else "?"
        status_style = "green" if status_val == "online" else "dim"
        table.add_row(
            name,
            getattr(dev, "protocol", "?"),
            getattr(dev, "ip", "?"),
            str(getattr(dev, "port", "?")),
            f"[{status_style}]{status_val}[/{status_style}]",
            cred_icon,
        )

    console.print(table)
