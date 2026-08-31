"""Glue: keep a MIDI input and an OBS connection alive, feed incoming events
through the rule table, dispatch the resulting actions. Never raises out of run()."""
from __future__ import annotations

import logging
import queue
import signal
import time

import mido

from .config import Config
from .mapping import RuleTable, to_event
from .obs_sink import ObsController

log = logging.getLogger("midi_pedald")

_PORT_POLL_S = 2.0
_DROP_TYPES = {"clock", "active_sensing"}


def find_input(substring: str) -> str | None:
    sub = substring.lower()
    for name in mido.get_input_names():
        if sub in name.lower():
            return name
    return None


class Daemon:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rules = RuleTable(cfg.rules)
        self.obs = ObsController(cfg.obs)
        self._q: queue.Queue = queue.Queue(maxsize=1000)
        self._port = None
        self._next_poll = 0.0
        self._stop = False

    def _on_midi(self, msg) -> None:
        # MIDI Clock / Active Sensing are dropped here, before logging or debounce.
        if msg.type in _DROP_TYPES:
            return
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            log.warning("event queue full; dropped %s", msg.type)

    def _ensure_port(self, now: float) -> None:
        if self._port is not None:
            if now >= self._next_poll:
                self._next_poll = now + _PORT_POLL_S
                if self._port.name not in mido.get_input_names():
                    log.info("MIDI input disappeared: %s", self._port.name)
                    self._close_port()
            return
        if now < self._next_poll:
            return
        self._next_poll = now + _PORT_POLL_S
        name = find_input(self.cfg.midi_port_substring)
        if name is None:
            return
        try:
            self._port = mido.open_input(name, callback=self._on_midi)
            log.info("MIDI input open: %s", name)
        except (OSError, RuntimeError) as e:
            log.info("failed to open MIDI input %s: %s", name, e)

    def _close_port(self) -> None:
        try:
            if self._port is not None:
                self._port.close()
        except Exception:
            pass
        self._port = None

    def _handle(self, msg) -> None:
        ev = to_event(msg)
        d = self.rules.decide(ev, time.monotonic())
        if d.action is None:
            log.debug("MIDI %s -> nothing (%s)", ev, d.reason)
            return
        log.debug("MIDI %s -> %s (%s)", ev, d.action, d.reason)
        self.obs.dispatch(d.action)

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        log.info(
            "midi-pedald starting (midi~=%r, obs=%s:%d)",
            self.cfg.midi_port_substring,
            self.cfg.obs.host,
            self.cfg.obs.port,
        )
        while not self._stop:
            try:
                now = time.monotonic()
                self._ensure_port(now)
                self.obs.ensure_connected(now)
                try:
                    msg = self._q.get(timeout=0.2)
                except queue.Empty:
                    continue
                self._handle(msg)
            except Exception:
                log.exception("main loop error; continuing")
                time.sleep(0.5)
        self._close_port()
        log.info("midi-pedald stopped")

    def _on_signal(self, *_a) -> None:
        self._stop = True
