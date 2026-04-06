"""Animated full-screen welcome with mouse-tracking mascot eyes."""

from __future__ import annotations

import random
import re
import threading
import time

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window, FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from iotcli import __version__
from iotcli.config.manager import ConfigManager
from iotcli.tui.banner import get_tip


# ── Constants ────────────────────────────────────────────────────────────────

MENU_ITEMS = [
    ("Discover devices on the network", "discover"),
    ("Import devices from cloud", "cloud-import"),
    ("Control a device", "control"),
    ("Check status of all devices", "status-all"),
    ("Setup wizard (add/configure)", "setup"),
    ("List configured devices", "list"),
    ("Generate AI agent skills", "skills"),
    ("Show help", "help"),
    ("Exit", "exit"),
]

SIGNALS = ["(( ))", "((·))", "((o))", "((O))", "((o))", "((·))"]

EYES = {
    "center": "O  O",
    "left":   "◄  ◄",
    "right":  "►  ►",
    "up":     "^  ^",
    "down":   "◡  ◡",
}
EYES_BLINK = "-  -"


# ── Animated welcome ────────────────────────────────────────────────────────


class AnimatedWelcome:
    """Full-screen TUI: mascot tracks mouse, eyes blink, signal pulses."""

    def __init__(self, config: ConfigManager, first_run: bool = True):
        self.config = config
        self.first_run = first_run
        self.selected = 0
        self.eye_dir = "center"
        self.blinking = first_run  # start with eyes closed on boot
        self.signal_idx = 0 if first_run else 3
        self.result: str | None = None
        self._done = False
        self._app: Application | None = None
        self._menu_start_y = 0

        # Device summary
        devices = config.get_all_devices()
        self.total = len(devices)
        self.online = sum(
            1 for d in devices.values()
            if getattr(d, "status", None) and d.status.value == "online"
        )
        self.offline = self.total - self.online

    # ── Rendering ────────────────────────────────────────────────────────

    def _mascot_lines(self) -> list[str]:
        signal = SIGNALS[self.signal_idx % len(SIGNALS)]
        eyes = EYES_BLINK if self.blinking else EYES.get(self.eye_dir, EYES["center"])
        return [
            f"      {signal} ",
            "    /--------\\",
            f"   /   {eyes}   \\",
            "  /____________\\",
            "  |  [======]  |",
            "  |  |      |  |",
            "  +--+------+--+",
        ]

    def _build_display(self) -> FormattedText:
        f: list[tuple[str, str]] = []

        mascot = self._mascot_lines()
        art_w = max(len(l) for l in mascot)
        gap = "      "

        # Right-side info (style, text) — None means device summary
        info: list[tuple[str, str] | None] = [
            ("bold ansibrightcyan", f"iotcli  v{__version__}"),
            ("ansigray", "──────────────────────────────"),
            ("ansigray", "Universal IoT device control"),
            ("ansigray", "for humans and AI agents"),
            ("", ""),
            None,
            ("", ""),
        ]

        rows = max(len(mascot), len(info))

        for i in range(rows):
            if i < len(mascot):
                f.append(("ansibrightcyan", mascot[i].ljust(art_w)))
            else:
                f.append(("", " " * art_w))
            f.append(("", gap))

            if i < len(info):
                item = info[i]
                if item is None:
                    self._append_summary(f)
                elif item[1]:
                    f.append(item)
            f.append(("", "\n"))

        # Tip
        tip_raw = get_tip()
        tip_clean = re.sub(r"\[/?bold\]", "", tip_raw)
        f.append(("", " " * art_w + gap))
        f.append(("ansigray", "Tip: "))
        f.append(("", tip_clean))
        f.append(("", "\n\n"))

        # Menu header
        f.append(("ansigray", "  ? "))
        f.append(("bold", "What would you like to do?\n"))
        f.append(("", "\n"))
        self._menu_start_y = rows + 4

        # Menu items
        for i, (label, _) in enumerate(MENU_ITEMS):
            if i == self.selected:
                f.append(("bold ansibrightcyan reverse", f"  ❯ {label}  "))
            else:
                f.append(("", f"    {label}  "))
            f.append(("", "\n"))

        f.append(("", "\n"))
        f.append(("ansigray", "  ↑↓ navigate  ⏎ select  q quit  "))
        f.append(("ansigray", "· mouse moves eyes"))

        return FormattedText(f)

    def _append_summary(self, f: list[tuple[str, str]]) -> None:
        if self.total == 0:
            f.append(("ansigray", "No devices yet — let's get started!"))
            return
        f.append(("bold", f"{self.total} device{'s' if self.total != 1 else ''}"))
        if self.online:
            f.append(("ansigray", "  ·  "))
            f.append(("bold ansibrightgreen", f"{self.online} online"))
        if self.offline:
            f.append(("ansigray", "  ·  "))
            f.append(("ansigray", f"{self.offline} offline"))

    # ── Mouse handler ────────────────────────────────────────────────────

    def _mouse_handler(self, mouse_event):
        x, y = mouse_event.position.x, mouse_event.position.y

        if mouse_event.event_type == MouseEventType.MOUSE_MOVE:
            # Eyes track cursor relative to mascot face (approx row 2, col 10)
            dx = x - 10
            dy = y - 2

            if abs(dx) < 4 and abs(dy) < 2:
                self.eye_dir = "center"
            elif abs(dx) > abs(dy) * 1.3:
                self.eye_dir = "right" if dx > 0 else "left"
            else:
                self.eye_dir = "down" if dy > 0 else "up"

        elif mouse_event.event_type == MouseEventType.MOUSE_UP:
            idx = y - self._menu_start_y
            if 0 <= idx < len(MENU_ITEMS):
                self.selected = idx
                self.result = MENU_ITEMS[idx][1]
                if self._app:
                    self._app.exit()

    # ── Animation threads ────────────────────────────────────────────────

    def _run_blink(self) -> None:
        time.sleep(0.1)  # let app start
        if self.first_run:
            # Boot: eyes closed, then open
            time.sleep(0.6)
            self.blinking = False
            if self._app:
                self._app.invalidate()
        while not self._done:
            time.sleep(random.uniform(3.0, 5.0))
            if self._done:
                break
            self.blinking = True
            if self._app:
                self._app.invalidate()
            time.sleep(0.15)
            self.blinking = False
            if self._app:
                self._app.invalidate()

    def _run_signal(self) -> None:
        time.sleep(0.1)
        if self.first_run:
            # Boot: sweep through signal strengths
            for i in range(len(SIGNALS)):
                if self._done:
                    return
                self.signal_idx = i
                if self._app:
                    self._app.invalidate()
                time.sleep(0.2)
            self.signal_idx = 3  # settle on strong
            if self._app:
                self._app.invalidate()
        while not self._done:
            time.sleep(1.0)
            if self._done:
                break
            self.signal_idx = (self.signal_idx + 1) % len(SIGNALS)
            if self._app:
                self._app.invalidate()

    # ── Run ──────────────────────────────────────────────────────────────

    def run(self) -> str | None:
        """Run the animated welcome screen. Returns action key or None."""
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _up(event):
            self.selected = (self.selected - 1) % len(MENU_ITEMS)

        @kb.add("down")
        @kb.add("j")
        def _down(event):
            self.selected = (self.selected + 1) % len(MENU_ITEMS)

        @kb.add("enter")
        def _enter(event):
            self.result = MENU_ITEMS[self.selected][1]
            event.app.exit()

        @kb.add("c-c")
        def _ctrl_c(event):
            self.result = None
            event.app.exit()

        @kb.add("q")
        def _quit(event):
            self.result = "exit"
            event.app.exit()

        # Subclass to intercept all mouse events for eye tracking
        welcome = self

        class _MouseTrackingControl(FormattedTextControl):
            def mouse_handler(self, mouse_event: MouseEvent):
                welcome._mouse_handler(mouse_event)
                return NotImplemented  # let prompt_toolkit handle the rest

        control = _MouseTrackingControl(
            self._build_display,
            focusable=True,
            show_cursor=False,
        )

        self._app = Application(
            layout=Layout(Window(content=control, always_hide_cursor=True)),
            key_bindings=kb,
            mouse_support=True,
            full_screen=True,
        )

        self._done = False
        t1 = threading.Thread(target=self._run_blink, daemon=True)
        t2 = threading.Thread(target=self._run_signal, daemon=True)
        t1.start()
        t2.start()

        try:
            self._app.run()
        finally:
            self._done = True

        return self.result


# ── Reusable animated picker ────────────────────────────────────────────────


class AnimatedPicker:
    """Full-screen picker with animated mascot — for sub-menus."""

    def __init__(self, title: str, choices: list[tuple[str, str]],
                 subtitle: str = "", show_back: bool = True):
        """
        Args:
            title: Header text (e.g. "Which device?")
            choices: List of (display_label, value) tuples
            subtitle: Optional secondary text below title
            show_back: Whether to add "← Back" option at the end
        """
        self.title = title
        self.subtitle = subtitle
        self.choices = list(choices)
        if show_back:
            self.choices.append(("← Back to main menu", "__back__"))
        self.selected = 0
        self.eye_dir = "center"
        self.blinking = False
        self.signal_idx = 3
        self.result: str | None = None
        self._done = False
        self._app: Application | None = None
        self._menu_start_y = 0

    def _mascot_lines(self) -> list[str]:
        signal = SIGNALS[self.signal_idx % len(SIGNALS)]
        eyes = EYES_BLINK if self.blinking else EYES.get(self.eye_dir, EYES["center"])
        return [
            f"      {signal}",
            "    /--------\\",
            f"   /   {eyes}   \\",
            "  /____________\\",
            "  |  [======]  |",
            "  |  |      |  |",
            "  +--+------+--+",
        ]

    def _build_display(self) -> FormattedText:
        f: list[tuple[str, str]] = []

        mascot = self._mascot_lines()
        art_w = max(len(l) for l in mascot)
        gap = "      "

        # Right-side: title + subtitle
        right: list[tuple[str, str]] = [
            ("bold ansibrightcyan", self.title),
        ]
        if self.subtitle:
            right.append(("ansigray", self.subtitle))

        rows = max(len(mascot), len(right))

        for i in range(rows):
            if i < len(mascot):
                f.append(("ansibrightcyan", mascot[i].ljust(art_w)))
            else:
                f.append(("", " " * art_w))
            f.append(("", gap))
            if i < len(right):
                f.append(right[i])
            f.append(("", "\n"))

        f.append(("", "\n"))
        self._menu_start_y = rows + 1

        for i, (label, value) in enumerate(self.choices):
            is_back = value == "__back__"
            if i == self.selected:
                f.append(("bold ansibrightcyan reverse", f"  ❯ {label}  "))
            elif is_back:
                f.append(("ansigray", f"    {label}  "))
            else:
                f.append(("", f"    {label}  "))
            f.append(("", "\n"))

        f.append(("", "\n"))
        f.append(("ansigray", "  ↑↓ navigate  ⏎ select  esc back  "))
        f.append(("ansigray", "· mouse moves eyes"))

        return FormattedText(f)

    def _mouse_handler(self, mouse_event):
        x, y = mouse_event.position.x, mouse_event.position.y

        if mouse_event.event_type == MouseEventType.MOUSE_MOVE:
            dx = x - 10
            dy = y - 2
            if abs(dx) < 4 and abs(dy) < 2:
                self.eye_dir = "center"
            elif abs(dx) > abs(dy) * 1.3:
                self.eye_dir = "right" if dx > 0 else "left"
            else:
                self.eye_dir = "down" if dy > 0 else "up"

        elif mouse_event.event_type == MouseEventType.MOUSE_UP:
            idx = y - self._menu_start_y
            if 0 <= idx < len(self.choices):
                self.selected = idx
                self.result = self.choices[idx][1]
                if self._app:
                    self._app.exit()

    def run(self) -> str | None:
        """Run the picker. Returns selected value, or None if back/cancel."""
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _up(event):
            self.selected = (self.selected - 1) % len(self.choices)

        @kb.add("down")
        @kb.add("j")
        def _down(event):
            self.selected = (self.selected + 1) % len(self.choices)

        @kb.add("enter")
        def _enter(event):
            self.result = self.choices[self.selected][1]
            event.app.exit()

        @kb.add("escape")
        @kb.add("c-c")
        def _back(event):
            self.result = None
            event.app.exit()

        picker = self

        class _MouseControl(FormattedTextControl):
            def mouse_handler(self, mouse_event: MouseEvent):
                picker._mouse_handler(mouse_event)
                return NotImplemented

        control = _MouseControl(
            self._build_display,
            focusable=True,
            show_cursor=False,
        )

        self._app = Application(
            layout=Layout(Window(content=control, always_hide_cursor=True)),
            key_bindings=kb,
            mouse_support=True,
            full_screen=True,
        )

        # Animation threads
        self._done = False

        def _blink():
            time.sleep(0.1)
            while not self._done:
                time.sleep(random.uniform(3.0, 5.0))
                if self._done:
                    break
                self.blinking = True
                if self._app:
                    self._app.invalidate()
                time.sleep(0.15)
                self.blinking = False
                if self._app:
                    self._app.invalidate()

        def _signal():
            time.sleep(0.1)
            while not self._done:
                time.sleep(1.0)
                if self._done:
                    break
                self.signal_idx = (self.signal_idx + 1) % len(SIGNALS)
                if self._app:
                    self._app.invalidate()

        t1 = threading.Thread(target=_blink, daemon=True)
        t2 = threading.Thread(target=_signal, daemon=True)
        t1.start()
        t2.start()

        try:
            self._app.run()
        finally:
            self._done = True

        if self.result == "__back__":
            return None
        return self.result


def animated_select(
    title: str,
    choices: list[tuple[str, str]],
    subtitle: str = "",
    show_back: bool = True,
) -> str | None:
    """Convenience function: full-screen animated picker.

    Returns selected value, or None if user pressed back/escape.
    """
    return AnimatedPicker(title, choices, subtitle, show_back=show_back).run()


# ── Full-screen task runner ────────────────────────────────────────────────


WORK_EYES = ["@  @", "◉  ◉", "⊙  ⊙"]


class TUITaskRunner:
    """Run a task in background, show animated mascot, then scrollable results.

    Usage::

        runner = TUITaskRunner("Network Discovery", "Scanning for IoT devices…")

        def task(r: TUITaskRunner):
            # do work …
            r.show_results(["Found 3 devices", "", "  lamp  miio  192.168.1.7"])

        runner.run(task)
    """

    def __init__(self, title: str, subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.phase: str = "working"  # "working" | "results"
        self.result_lines: list[str] = []
        self.scroll_offset = 0
        # animation state
        self.eye_dir = "center"
        self.blinking = False
        self.signal_idx = 3
        self._work_frame = 0
        self._done_flag = False
        self._app: Application | None = None

    # ── rendering ────────────────────────────────────────────────────

    def _mascot_lines(self) -> list[str]:
        signal = SIGNALS[self.signal_idx % len(SIGNALS)]
        if self.phase == "working":
            eyes = WORK_EYES[self._work_frame % len(WORK_EYES)]
        else:
            eyes = EYES_BLINK if self.blinking else EYES.get(self.eye_dir, EYES["center"])
        return [
            f"      {signal}",
            "    /--------\\",
            f"   /   {eyes}   \\",
            "  /____________\\",
            "  |  [======]  |",
            "  |  |      |  |",
            "  +--+------+--+",
        ]

    def _build_display(self) -> FormattedText:
        f: list[tuple[str, str]] = []
        mascot = self._mascot_lines()
        art_w = max(len(l) for l in mascot)
        gap = "      "

        # Right-side header
        right: list[tuple[str, str]] = [
            ("bold ansibrightcyan", self.title),
        ]
        if self.subtitle:
            right.append(("ansigray", self.subtitle))

        if self.phase == "working":
            dots = "." * ((self._work_frame % 3) + 1)
            right.append(("", ""))
            right.append(("bold ansibrightyellow", f"Working{dots.ljust(3)}"))

        rows = max(len(mascot), len(right))
        for i in range(rows):
            if i < len(mascot):
                f.append(("ansibrightcyan", mascot[i].ljust(art_w)))
            else:
                f.append(("", " " * art_w))
            f.append(("", gap))
            if i < len(right):
                f.append(right[i])
            f.append(("", "\n"))

        f.append(("", "\n"))

        if self.phase == "results":
            # Calculate visible height
            visible_h = 15
            if self._app:
                try:
                    visible_h = self._app.output.get_size().rows - rows - 5
                    visible_h = max(visible_h, 5)
                except Exception:
                    visible_h = 15

            visible = self.result_lines[self.scroll_offset:self.scroll_offset + visible_h]
            for line in visible:
                f.append(("", f"  {line}\n"))

            # Scroll indicator
            total = len(self.result_lines)
            f.append(("", "\n"))
            if total > visible_h:
                top = self.scroll_offset + 1
                bot = min(self.scroll_offset + visible_h, total)
                f.append(("ansigray", f"  [{top}–{bot} of {total}]  ↑↓ scroll  "))
            else:
                f.append(("ansigray", "  "))
            f.append(("ansigray", "Enter/Esc back to menu"))
        else:
            f.append(("ansigray", "  Ctrl+C to cancel"))

        return FormattedText(f)

    # ── public API (called from task thread) ─────────────────────────

    def show_results(self, lines: list[str]) -> None:
        """Transition from 'working' to 'results' — called from task thread."""
        self.result_lines = lines
        self.phase = "results"
        self.scroll_offset = 0
        if self._app:
            self._app.invalidate()

    # ── mouse ────────────────────────────────────────────────────────

    def _mouse_handler(self, mouse_event: MouseEvent) -> None:
        if mouse_event.event_type == MouseEventType.MOUSE_MOVE:
            x, y = mouse_event.position.x, mouse_event.position.y
            dx, dy = x - 10, y - 2
            if abs(dx) < 4 and abs(dy) < 2:
                self.eye_dir = "center"
            elif abs(dx) > abs(dy) * 1.3:
                self.eye_dir = "right" if dx > 0 else "left"
            else:
                self.eye_dir = "down" if dy > 0 else "up"
        elif mouse_event.event_type == MouseEventType.MOUSE_UP:
            # scroll via mouse wheel is handled by up/down keys
            pass

    # ── run ──────────────────────────────────────────────────────────

    def run(self, task_fn) -> None:
        """Run *task_fn(self)* in background; block until user dismisses results."""
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _up(event):
            if self.phase == "results" and self.scroll_offset > 0:
                self.scroll_offset -= 1

        @kb.add("down")
        @kb.add("j")
        def _down(event):
            if self.phase == "results":
                visible_h = 15
                try:
                    visible_h = max(event.app.output.get_size().rows - 14, 5)
                except Exception:
                    pass
                max_off = max(0, len(self.result_lines) - visible_h)
                if self.scroll_offset < max_off:
                    self.scroll_offset += 1

        @kb.add("pageup")
        def _pgup(event):
            if self.phase == "results":
                self.scroll_offset = max(0, self.scroll_offset - 10)

        @kb.add("pagedown")
        def _pgdn(event):
            if self.phase == "results":
                visible_h = 15
                try:
                    visible_h = max(event.app.output.get_size().rows - 14, 5)
                except Exception:
                    pass
                max_off = max(0, len(self.result_lines) - visible_h)
                self.scroll_offset = min(max_off, self.scroll_offset + 10)

        @kb.add("enter")
        @kb.add("escape")
        def _back(event):
            if self.phase == "results":
                event.app.exit()

        @kb.add("c-c")
        def _cancel(event):
            event.app.exit()

        runner = self

        class _MouseCtrl(FormattedTextControl):
            def mouse_handler(self, mouse_event: MouseEvent):
                runner._mouse_handler(mouse_event)
                return NotImplemented

        control = _MouseCtrl(self._build_display, focusable=True, show_cursor=False)

        self._app = Application(
            layout=Layout(Window(content=control, always_hide_cursor=True)),
            key_bindings=kb,
            mouse_support=True,
            full_screen=True,
        )

        self._done_flag = False

        def _blink():
            time.sleep(0.3)
            while not self._done_flag:
                time.sleep(random.uniform(3.0, 5.0))
                if self._done_flag:
                    break
                self.blinking = True
                if self._app:
                    self._app.invalidate()
                time.sleep(0.15)
                self.blinking = False
                if self._app:
                    self._app.invalidate()

        def _signal():
            time.sleep(0.3)
            while not self._done_flag:
                time.sleep(1.0)
                if self._done_flag:
                    break
                self.signal_idx = (self.signal_idx + 1) % len(SIGNALS)
                if self._app:
                    self._app.invalidate()

        def _work_anim():
            while not self._done_flag and self.phase == "working":
                time.sleep(0.5)
                self._work_frame += 1
                if self._app:
                    self._app.invalidate()

        def _run_task():
            try:
                task_fn(runner)
            except Exception as e:
                runner.show_results([f"Error: {e}"])

        for fn in (_blink, _signal, _work_anim, _run_task):
            threading.Thread(target=fn, daemon=True).start()

        try:
            self._app.run()
        finally:
            self._done_flag = True
