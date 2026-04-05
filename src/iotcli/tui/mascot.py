"""Homie -- the iotcli mascot. A smart house with eyes and a Wi-Fi antenna."""

from __future__ import annotations

from enum import Enum

from rich.console import Console
from rich.text import Text

console = Console()


class MascotMood(Enum):
    HAPPY = "happy"
    WORKING = "working"
    ERROR = "error"
    SLEEPING = "sleeping"


# Full-size ASCII art per mood (~7 lines, ~18 cols wide)
MASCOT_ART: dict[MascotMood, str] = {
    MascotMood.HAPPY: """\
      ((o))
    /--------\\
   /   O  O   \\
  /____________\\
  |  [======]  |
  |  |  ◡◡  |  |
  +--+------+--+""",

    MascotMood.WORKING: """\
      ((o))
    /--------\\
   /   @  @   \\
  /____________\\
  |  [======]  |
  |  |  ..  |  |
  +--+------+--+""",

    MascotMood.ERROR: """\
      ((x))
    /-------\\
   /   >  <   \\
  /____________\\
  |  [======]  |
  |  |  ><  |  |
  +--+------+--+""",

    MascotMood.SLEEPING: """\
      (( ))
    /--------\\
   /   -  -   \\
  /____________\\
  |  [======]  |
  |  |  zZ  |  |
  +--+------+--+""",
}

# Colors for each mood's art
_MOOD_STYLE: dict[MascotMood, str] = {
    MascotMood.HAPPY: "cyan",
    MascotMood.WORKING: "blue",
    MascotMood.ERROR: "red",
    MascotMood.SLEEPING: "dim",
}

# Mini inline variants (single-line, for messages)
MASCOT_MINI: dict[MascotMood, str] = {
    MascotMood.HAPPY: "[cyan][~] ^_^[/cyan]",
    MascotMood.WORKING: "[blue][~] . .[/blue]",
    MascotMood.ERROR: "[red][~] >_<[/red]",
    MascotMood.SLEEPING: "[dim][~] -_-[/dim]",
}


def render_full(mood: MascotMood = MascotMood.HAPPY) -> Text:
    """Return the full-size mascot as a Rich Text object."""
    art = MASCOT_ART.get(mood, MASCOT_ART[MascotMood.HAPPY])
    style = _MOOD_STYLE.get(mood, "cyan")
    return Text(art, style=style)


def render_inline(mood: MascotMood, message: str) -> str:
    """Return a Rich markup string with mini mascot + message."""
    mini = MASCOT_MINI.get(mood, MASCOT_MINI[MascotMood.HAPPY])
    return f"  {mini}  {message}"


def render_side_by_side(mood: MascotMood, right_lines: list[str]) -> Text:
    """Render mascot art on the left, text lines on the right, aligned."""
    art = MASCOT_ART.get(mood, MASCOT_ART[MascotMood.HAPPY])
    style = _MOOD_STYLE.get(mood, "cyan")
    art_lines = art.splitlines()

    # Pad art lines to consistent width
    art_width = max(len(line) for line in art_lines)
    gap = "      "  # space between art and text

    combined = Text()
    max_rows = max(len(art_lines), len(right_lines))

    for i in range(max_rows):
        # Left side: mascot art
        if i < len(art_lines):
            combined.append(art_lines[i].ljust(art_width), style=style)
        else:
            combined.append(" " * art_width)

        combined.append(gap)

        # Right side: text content
        if i < len(right_lines):
            combined.append_text(Text.from_markup(right_lines[i]))

        if i < max_rows - 1:
            combined.append("\n")

    return combined


def fits_terminal(min_width: int = 60) -> bool:
    """Check if terminal is wide enough for full mascot art."""
    return console.width >= min_width
