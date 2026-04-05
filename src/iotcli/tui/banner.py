"""iotcli brand assets -- tips, version display, tagline."""

from __future__ import annotations

import datetime

from iotcli import __version__

TIPS: list[str] = [
    "[bold]iotcli --json[/bold] for AI agent output",
    "[bold]iotcli skills generate[/bold] for agent skills",
    "[bold]--verbose[/bold] on any command for details",
    "[bold]iotcli discover[/bold] to find new devices",
    "[bold]iotcli control on <device>[/bold] for quick control",
    "[bold]iotcli status-all[/bold] to check everything",
    "[bold]pipx install iotcli[/bold] for global install",
    "Credentials are always encrypted",
]


def get_tip() -> str:
    """Return a deterministic daily tip."""
    day = datetime.date.today().toordinal()
    return TIPS[day % len(TIPS)]


def version_line() -> str:
    """Formatted version string with Rich markup."""
    return f"[bold cyan]iotcli[/bold cyan]  [dim]v{__version__}[/dim]"


def tagline() -> list[str]:
    """Return tagline as separate lines for side-by-side layout."""
    return [
        "[dim]Universal IoT device control[/dim]",
        "[dim]for humans and AI agents[/dim]",
    ]
