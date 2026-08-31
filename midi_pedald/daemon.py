"""Glue: keep a MIDI input and every sink alive, feed incoming events through the
rule table, dispatch each matching rule to its sink. Never raises out of run()."""
from __future__ import annotations

import logging
import queue
import signal
import time

import mido

from .bpm import BpmMeter
from .config import Config
from .mapping import RuleTable, to_event
from .midi_sink import MidiSink
from .obs_sink import ObsController

log = logging.getLogger("midi_pedald")

_PORT_POLL_S = 2.0


def find_input(substring: str) -> str | None:
    sub = substring.lower()
    for name in mido.get_input_names():
        if sub in name.lower():
            return name
    return None


# Sink contract (informal — two implementations, so no ABC; documented here):
#   ensure_connected(now) -> bool    own backoff/poll; never raises
#   dispatch(method, **params)       no-op + one log line when disconnected; never raises
#   connected -> bool                for logging only
_SINK_BUILDERS = {
    "obs": ObsController,
    "midi_out": MidiSink,
}


def _build_sinks(cfg: Config, builders: dict | None = None) -> dict[str, object]:
    """Construct each configured sink from its config block. A sink that fails to
    build is logged and skipped so the others still run."""
    builders = builders or _SINK_BUILDERS
    out: dict[str, object] = {}
    for name, sink_cfg in cfg.sinks.items():
        try:
            out[name] = builders[name](sink_cfg)
        except Exception:
            log.exception("sink %r failed to initialise; continuing without it", name)
    return out


class Daemon:
    def __init__(self, cfg: Config, sinks: dict[str, object] | None = None):
        self.cfg = cfg
        self.rules = RuleTable(cfg.rules)
        self.sinks = sinks if sinks is not None else _build_sinks(cfg)
        self._bpm = (
            BpmMeter(cfg.bpm.window_ticks, cfg.bpm.tolerance, cfg.bpm.confirm_windows)
            if cfg.bpm.enabled
            else None
        )
        self._q: queue.Queue = queue.Queue(maxsize=1000)
        self._port = None
        self._next_poll = 0.0
        self._stop = False

    def _on_midi(self, msg) -> None:
        # MIDI Clock feeds the BPM meter here, then is dropped before the queue -
        # the "clock never reaches any logic" guarantee is preserved.
        if msg.type == "clock":
            if self._bpm is not None:
                bpm = self._bpm.tick()
                if bpm is not None:
                    log.info("BPM ~%.1f", bpm)
            return
        if msg.type == "active_sensing":
            return
        if msg.type == "start" and self._bpm is not None:
            self._bpm.reset()
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
        decisions = self.rules.decide_all(ev, time.monotonic())
        if not decisions:
            log.debug("MIDI %s -> nothing (no rule matched)", ev)
            return
        for d in decisions:
            sink = self.sinks.get(d.sink)
            if sink is None:
                # config validation rejects this, so only reachable if the sink
                # failed to build at startup.
                log.warning("rule %d: sink %r unavailable, dropping %s", d.rule_index, d.sink, d.method)
                continue
            log.debug("MIDI %s -> %s.%s (%s)", ev, d.sink, d.method, d.reason)
            sink.dispatch(d.method, **d.params)

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)
        log.info(
            "midi-pedald starting (midi~=%r, sinks=[%s])",
            self.cfg.midi_port_substring,
            ", ".join(self.sinks) or "none",
        )
        while not self._stop:
            try:
                now = time.monotonic()
                self._ensure_port(now)
                for sink in self.sinks.values():
                    sink.ensure_connected(now)
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
