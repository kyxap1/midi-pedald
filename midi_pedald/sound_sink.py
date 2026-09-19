"""Sound sink: a short blip through afplay, so a pedal press is confirmed
without looking at the screen.

afplay has no device flag — it always plays to the default output device. When
that device is the one you record (an interface loopback), the blip is kept out
of the take by rule order, not by volume: put `sound.play` *before*
`obs.start_record` and *after* `obs.stop_record`.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("midi_pedald")

_AFPLAY = "/usr/bin/afplay"
_SYSTEM_SOUNDS = Path("/System/Library/Sounds")
# A blip is a fraction of a second; this only bounds a wedged afplay, which
# would otherwise stall the dispatch loop for good.
_TIMEOUT_S = 5.0

# Methods this sink exposes to rules as "sound.<name>".
SOUND_METHODS = frozenset({"play"})


def resolve_sound(name: str) -> Path:
    """A bare name is one of the macOS system sounds; anything with a separator
    is a path of your own."""
    if "/" in name:
        return Path(name).expanduser()
    return _SYSTEM_SOUNDS / f"{name}.aiff"


class SoundSink:
    def __init__(self, cfg, runner=subprocess.run):
        self.volume = cfg.volume
        self.max_ms = cfg.max_ms
        self._run = runner

    @property
    def connected(self) -> bool:
        return True

    def ensure_connected(self, now: float | None = None) -> bool:
        return True

    def dispatch(self, method: str, **params) -> None:
        if method != "play":
            log.error("unknown sound method: %s", method)
            return
        self._play(**params)

    def _play(self, file: str) -> None:
        path = resolve_sound(file)
        # -t truncates playback: the shortest stock sound is 0.56s, and every
        # one of those seconds is added to the start of the take it precedes.
        cmd = [_AFPLAY, "-v", str(self.volume), "-t", f"{self.max_ms / 1000:.3f}", str(path)]
        # Synchronous on purpose: the blip must be over before the next rule in
        # the file runs, or a take starting right after would record it.
        try:
            r = self._run(cmd, timeout=_TIMEOUT_S, capture_output=True)
        except Exception as e:
            log.info("afplay %s failed: %s", path, e)
            return
        if r.returncode:
            log.info("afplay %s failed (exit %s)", path, r.returncode)
