import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import midi_pedald.daemon as daemon  # noqa: E402
from midi_pedald.config import Config, LogConfig, ObsConfig  # noqa: E402
from midi_pedald.daemon import Daemon, _build_sinks  # noqa: E402
from midi_pedald.mapping import Rule  # noqa: E402
from tests.fakes import FakeMido, FakeSink, clock, start  # noqa: E402

# These tests never touch a real MIDI backend.
daemon.mido = FakeMido()


def cfg(rules=None, sinks=None):
    return Config(
        midi_port_substring="Scarlett",
        sinks=sinks if sinks is not None else {"obs": ObsConfig()},
        log=LogConfig(),
        rules=rules or [Rule("start", "obs.start_record")],
    )


def test_build_sinks_skips_a_sink_that_fails_to_build():
    def boom(_cfg):
        raise RuntimeError("no bus")

    c = cfg(sinks={"good": ObsConfig(), "bad": ObsConfig()})
    sinks = _build_sinks(c, {"good": lambda sc: FakeSink(), "bad": boom})
    assert set(sinks) == {"good"}


def test_surviving_sink_still_receives_dispatch_after_a_sibling_fails_to_build():
    def boom(_cfg):
        raise RuntimeError("no bus")

    c = cfg(sinks={"obs": ObsConfig(), "bad": ObsConfig()})
    sinks = _build_sinks(c, {"obs": lambda sc: FakeSink(), "bad": boom})
    Daemon(c, sinks=sinks)._handle(start())
    assert sinks["obs"].calls == [("start_record", {})]


def test_handle_dispatches_to_the_obs_sink():
    s = FakeSink()
    Daemon(cfg(), sinks={"obs": s})._handle(start())
    assert s.calls == [("start_record", {})]


def test_handle_with_empty_registry_drops_without_crashing():
    Daemon(cfg(), sinks={})._handle(start())  # must not raise


def test_clock_feeds_the_meter_and_never_reaches_the_queue():
    dae = Daemon(cfg(), sinks={"obs": FakeSink()})
    assert dae._bpm is not None
    dae._on_midi(clock())
    assert dae._q.qsize() == 0


def test_clock_with_meter_disabled_touches_no_bpm_state():
    c = cfg()
    c.bpm.enabled = False
    dae = Daemon(c, sinks={"obs": FakeSink()})
    assert dae._bpm is None
    dae._on_midi(clock())  # must not raise
    assert dae._q.qsize() == 0


def test_start_is_queued_and_resets_the_meter_window():
    dae = Daemon(cfg(), sinks={"obs": FakeSink()})
    dae._bpm._t0 = 123.0
    dae._on_midi(start())
    assert dae._q.qsize() == 1
    assert dae._bpm._t0 is None


def test_input_enumeration_error_is_swallowed_not_raised():
    # rtmidi raises InvalidPortError when a device is unplugged mid-scan; the
    # daemon must see an empty list, not a traceback in the log.
    class Angry:
        def get_input_names(self):
            raise RuntimeError("portNumber (1) is invalid")

    saved = daemon.mido
    daemon.mido = Angry()
    try:
        assert daemon._input_names() == []
        assert daemon.find_input("Scarlett") is None
    finally:
        daemon.mido = saved


def test_open_input_raising_invalidporterror_does_not_propagate():
    # InvalidPortError is a ValueError; the daemon must log and retry, not crash.
    fm = FakeMido(inputs=["Scarlett 18i16 4th Gen"])

    def boom(name, callback=None):
        raise ValueError("portNumber (1) is invalid")

    fm.open_input = boom
    saved = daemon.mido
    daemon.mido = fm
    try:
        dae = Daemon(cfg(), sinks={"obs": FakeSink()})
        dae._ensure_port(0.0)  # must not raise
        assert dae._port is None
    finally:
        daemon.mido = saved


class FakeObs(FakeSink):
    """A FakeSink that also answers the obs-only record_active() probe."""

    def __init__(self, record=None):
        super().__init__()
        self.record = record  # None = OBS unreachable
        self.probes = 0

    def record_active(self):
        self.probes += 1
        return self.record


def daemon_with_overlay(record):
    c = cfg(
        rules=[Rule("start", "obs.start_record"), Rule("start", "overlay.show")],
        sinks={"obs": ObsConfig(), "overlay": ObsConfig()},
    )
    obs, overlay = FakeObs(record), FakeSink()
    return Daemon(c, sinks={"obs": obs, "overlay": overlay}), obs, overlay


def test_overlay_follows_obs_recording():
    dae, _, overlay = daemon_with_overlay(True)
    dae._sync_overlay(0.0)
    assert overlay.calls == [("show", {})]


def test_overlay_is_cleared_when_obs_is_not_recording():
    dae, _, overlay = daemon_with_overlay(False)
    dae._sync_overlay(0.0)
    assert overlay.calls == [("hide", {})]


def test_overlay_is_left_alone_when_obs_state_is_unknown():
    dae, _, overlay = daemon_with_overlay(None)
    dae._sync_overlay(0.0)
    assert overlay.calls == []


def test_obs_state_is_not_polled_faster_than_the_interval():
    dae, obs, _ = daemon_with_overlay(False)
    dae._sync_overlay(0.0)
    dae._sync_overlay(0.1)
    assert obs.probes == 1
    dae._sync_overlay(daemon._RECORD_POLL_S)
    assert obs.probes == 2


def test_overlay_rules_are_suppressed_while_obs_owns_the_dot():
    dae, obs, overlay = daemon_with_overlay(False)
    dae._sync_overlay(0.0)
    overlay.calls.clear()
    dae._handle(start())
    assert obs.calls == [("start_record", {})]  # the obs rule still fires
    assert overlay.calls == []  # the dot stays OBS's to set


def test_overlay_rules_drive_the_dot_again_once_obs_goes_away():
    dae, obs, overlay = daemon_with_overlay(True)
    dae._sync_overlay(0.0)
    obs.record = None
    dae._sync_overlay(daemon._RECORD_POLL_S)
    overlay.calls.clear()
    dae._handle(start())
    assert overlay.calls == [("show", {"color": "blue"})]


def test_overlay_rules_light_the_dot_blue_without_an_obs_sink():
    c = cfg(rules=[Rule("start", "overlay.show")], sinks={"overlay": ObsConfig()})
    overlay = FakeSink()
    Daemon(c, sinks={"overlay": overlay})._handle(start())
    assert overlay.calls == [("show", {"color": "blue"})]


def test_obs_is_not_polled_without_an_overlay_sink():
    obs = FakeObs(True)
    Daemon(cfg(), sinks={"obs": obs})._sync_overlay(0.0)
    assert obs.probes == 0


def test_run_pumps_ensure_connected_on_every_sink_then_stops_cleanly():
    a = FakeSink()

    class Stopper:
        connected = True

        def ensure_connected(self, now):
            dae._stop = True
            return True

        def dispatch(self, method, **params):
            pass

    dae = Daemon(cfg(), sinks={"a": a, "z": Stopper()})
    dae.run()
    assert a.ensure_calls == 1


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
