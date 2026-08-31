"""Clock -> BPM: pure logic, no third-party imports, so it tests on plain
python3. Fed one `tick()` per MIDI Clock byte (0xF8, 24 per quarter note) from
the rtmidi callback thread, before the clock is dropped. All state is touched
from that one thread only.

The latch only moves when a new tempo clears the dead-band for
`confirm_windows` consecutive windows — tempo here changes by tap between
takes (discrete steps with a constant between them), not as a noisy signal, so
there is nothing to filter and no median-of-deltas.
"""
from __future__ import annotations

import time

_PPQN = 24
_LO_BPM = 40.0
_HI_BPM = 250.0


class BpmMeter:
    def __init__(
        self,
        window_ticks: int = 96,
        tolerance: float = 1.5,
        confirm_windows: int = 2,
        now=time.monotonic,
        lo: float = _LO_BPM,
        hi: float = _HI_BPM,
    ):
        self.window_ticks = window_ticks
        self.tolerance = tolerance
        self.confirm_windows = confirm_windows
        self._now = now
        self.lo = lo
        self.hi = hi
        self.latched: float | None = None
        self._t0: float | None = None
        self._n = 0
        self._cand: float | None = None
        self._cand_n = 0

    def reset(self) -> None:
        """MIDI Start (0xFA): drop the partial window; the latch is kept."""
        self._t0 = None
        self._n = 0

    def tick(self) -> float | None:
        t = self._now()
        if self._t0 is None:  # window origin; not counted, so W ticks span W intervals
            self._t0 = t
            self._n = 0
            return None
        self._n += 1
        if self._n < self.window_ticks:
            return None
        elapsed = t - self._t0
        self._t0 = t
        self._n = 0
        if elapsed <= 0:
            return None
        bpm = 60.0 * self.window_ticks / (_PPQN * elapsed)
        if not (self.lo <= bpm <= self.hi):
            return None  # implausible window discarded; latch and candidate untouched
        return self._on_window(bpm)

    def _on_window(self, bpm: float) -> float | None:
        if self.latched is None:
            self.latched = bpm
            return bpm
        if abs(bpm - self.latched) <= self.tolerance:
            self._cand = None
            self._cand_n = 0
            return None
        if self._cand is not None and abs(bpm - self._cand) <= self.tolerance:
            self._cand_n += 1
        else:
            self._cand = bpm
            self._cand_n = 1
        if self._cand_n >= self.confirm_windows:
            self.latched = bpm
            self._cand = None
            self._cand_n = 0
            return bpm
        return None
