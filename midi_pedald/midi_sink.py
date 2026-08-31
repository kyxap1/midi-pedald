"""MIDI output sink: hold an output port open on a substring-matched device,
reopen it when it disappears, emit timed CC sequences.

`mido` is injected (or imported lazily on first use) so config validation can
read METHOD names without the backend installed. Never raises out of
`dispatch` / `ensure_connected`.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("midi_pedald")

_PORT_POLL_S = 2.0
_CHANNEL = 0  # only channel 1 is used; a config knob lands here if Waveform needs it

# Methods this sink exposes to rules as "midi_out.<name>".
MIDI_OUT_METHODS = frozenset({"cc_sequence"})


class MidiSink:
    def __init__(self, cfg, backend=None, now=time.monotonic):
        self.substring = cfg.port_substring.lower()
        self._mido = backend
        self._now = now
        self._port = None
        self._next_poll = 0.0

    @property
    def connected(self) -> bool:
        return self._port is not None

    def _backend(self):
        if self._mido is None:
            import mido

            self._mido = mido
        return self._mido

    def _output_names(self) -> list[str]:
        try:
            return list(self._backend().get_output_names())
        except Exception:
            return []

    def _match(self) -> str | None:
        for n in self._output_names():
            if self.substring in n.lower():
                return n
        return None

    def _close(self) -> None:
        try:
            if self._port is not None:
                self._port.close()
        except Exception:
            pass
        self._port = None

    def ensure_connected(self, now: float | None = None) -> bool:
        now = self._now() if now is None else now
        if self._port is not None:
            if now >= self._next_poll:
                self._next_poll = now + _PORT_POLL_S
                if self._port.name not in self._output_names():
                    log.info("MIDI output disappeared: %s", self._port.name)
                    self._close()
            return self._port is not None
        if now < self._next_poll:
            return False
        self._next_poll = now + _PORT_POLL_S
        name = self._match()
        if name is None:
            return False
        try:
            self._port = self._backend().open_output(name)
            log.info("MIDI output open: %s", name)
            return True
        except (OSError, RuntimeError, ValueError) as e:
            # ValueError covers rtmidi's InvalidPortError when the device
            # vanishes between the match and open; retried on the next poll.
            log.info("failed to open MIDI output %s: %s", name, e)
            return False

    def dispatch(self, method: str, **params) -> None:
        if method != "cc_sequence":
            log.error("unknown midi_out method: %s", method)
            return
        self._cc_sequence(**params)

    def _cc_sequence(self, cc, gap_ms: int = 0) -> None:
        if not cc:
            return
        if not self.ensure_connected():
            log.info("skipping cc_sequence: MIDI output not connected")
            return
        try:
            msg = self._backend().Message
            for i, (num, val) in enumerate(cc):
                if i:
                    time.sleep(gap_ms / 1000)
                self._port.send(msg("control_change", channel=_CHANNEL, control=num, value=val))
        except Exception as e:
            log.info("MIDI output send failed: %s; dropping port", e)
            self._close()
