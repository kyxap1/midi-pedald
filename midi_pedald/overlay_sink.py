"""Overlay sink: a dot above every window, so a pedal press is visible without
looking away from the game or the instrument.

The drawing lives in a small Swift helper rather than in-process: AppKit needs
to own the main thread's run loop, and the daemon's dispatch loop already does.
The helper exits when its stdin closes, so the dot cannot outlive the daemon.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("midi_pedald")

_HELPER = "overlay-dot"
# The helper only has a window to tear down; this bounds a wedged one before
# falling back to kill.
_EXIT_S = 2.0

# Methods this sink exposes to rules as "overlay.<name>".
OVERLAY_METHODS = frozenset({"show", "hide"})


def helper_path() -> Path:
    """Frozen, the helper sits beside the daemon executable; from a source tree
    it is whatever build-pkg.sh compiled last."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / _HELPER
    return Path(__file__).resolve().parents[1] / "build" / _HELPER


class OverlaySink:
    def __init__(self, cfg, spawn=subprocess.Popen):
        self.cfg = cfg
        self._spawn = spawn
        self._proc = None

    @property
    def connected(self) -> bool:
        return True

    def ensure_connected(self, now: float | None = None) -> bool:
        return True

    def dispatch(self, method: str, **params) -> None:
        if method == "show":
            self._show()
        elif method == "hide":
            self._hide()
        else:
            log.error("unknown overlay method: %s", method)

    def _show(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        cmd = [
            str(helper_path()),
            "--size", str(self.cfg.size_px),
            "--right", str(self.cfg.right_px),
            "--ring", str(self.cfg.ring_px),
        ]
        if self.cfg.top_px is not None:
            cmd += ["--top", str(self.cfg.top_px)]
        try:
            self._proc = self._spawn(cmd, stdin=subprocess.PIPE)
        except Exception as e:
            log.error("overlay failed to start: %s", e)
            self._proc = None

    def _hide(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
            proc.wait(timeout=_EXIT_S)
        except Exception:
            proc.kill()
