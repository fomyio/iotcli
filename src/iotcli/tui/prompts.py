"""Rich + InquirerPy prompt helpers — consistent TUI building blocks."""

from __future__ import annotations

from typing import Any

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


# -- simple wrappers ----------------------------------------------------------


def header(title: str, subtitle: str = "") -> None:
    """Print a styled section header."""
    content = Text(title, style="bold cyan")
    if subtitle:
        content.append(f"\n{subtitle}", style="dim")
    console.print(Panel(content, border_style="blue", expand=False))


def mascot_header(title: str, subtitle: str = "", mood=None) -> None:
    """Print a section header with Homie mascot alongside."""
    from iotcli.tui.mascot import MascotMood, render_side_by_side, fits_terminal

    if mood is None:
        mood = MascotMood.HAPPY

    right_lines = [f"[bold cyan]{title}[/bold cyan]"]
    if subtitle:
        right_lines.append(f"[dim]{subtitle}[/dim]")

    if fits_terminal(60):
        content = render_side_by_side(mood, right_lines)
    else:
        content = Text(title, style="bold cyan")
        if subtitle:
            content.append(f"\n{subtitle}", style="dim")

    console.print(Panel(content, border_style="blue", expand=False))


def success(msg: str, with_mascot: bool = False) -> None:
    if with_mascot:
        from iotcli.tui.mascot import MascotMood, render_inline
        console.print(render_inline(MascotMood.HAPPY, msg))
    else:
        console.print(f"  [green]>[/green] {msg}")


def warn(msg: str) -> None:
    console.print(f"  [yellow]![/yellow] {msg}")


def error(msg: str, with_mascot: bool = False) -> None:
    if with_mascot:
        from iotcli.tui.mascot import MascotMood, render_inline
        console.print(render_inline(MascotMood.ERROR, msg))
    else:
        console.print(f"  [red]x[/red] {msg}")


def info(msg: str) -> None:
    console.print(f"  [dim]>[/dim] {msg}")


def step(n: int, total: int, label: str) -> None:
    console.print(f"\n  [bold cyan]Step {n}/{total}[/bold cyan]  {label}")


# -- InquirerPy wrappers -----------------------------------------------------


def select(message: str, choices: list[str | dict], **kw) -> str:
    """Fuzzy-searchable selection list."""
    return inquirer.fuzzy(
        message=message,
        choices=choices,
        border=True,
        **kw,
    ).execute()


def text(message: str, default: str = "", validate: Any = None, **kw) -> str:
    """Text input with optional validation."""
    return inquirer.text(
        message=message,
        default=default,
        validate=validate,
        **kw,
    ).execute()


def secret(message: str, **kw) -> str:
    """Password / token input (masked)."""
    return inquirer.secret(
        message=message,
        **kw,
    ).execute()


def confirm(message: str, default: bool = True) -> bool:
    return inquirer.confirm(message=message, default=default).execute()


def number(message: str, default: int = 0, **kw) -> int:
    return int(
        inquirer.number(message=message, default=default, **kw).execute()
    )


# -- device table -------------------------------------------------------------


def device_table(devices: list[dict[str, Any]], title: str = "Devices") -> None:
    """Pretty-print a list of device dicts."""
    table = Table(title=title, border_style="blue", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Protocol", style="cyan")
    table.add_column("IP")
    table.add_column("Status")
    table.add_column("Missing", style="yellow")

    for i, d in enumerate(devices, 1):
        status_style = "green" if d.get("status") == "online" else "dim"
        missing = ", ".join(d.get("missing_info", []))
        table.add_row(
            str(i),
            d.get("name", "?"),
            d.get("protocol", "?"),
            d.get("ip", "?"),
            f"[{status_style}]{d.get('status', '?')}[/{status_style}]",
            missing or "-",
        )

    console.print(table)


def status_panel(name: str, status: dict[str, Any]) -> None:
    """Print a single device status as a panel."""
    online = status.get("online", False)
    border = "green" if online else "red"
    title = f"{name} — {'online' if online else 'offline'}"

    lines: list[str] = []
    for k, v in status.items():
        if k in ("online", "dps"):
            continue
        lines.append(f"  [bold]{k}:[/bold] {v}")

    body = "\n".join(lines) if lines else "  [dim]no data[/dim]"
    console.print(Panel(body, title=title, border_style=border, expand=False))
