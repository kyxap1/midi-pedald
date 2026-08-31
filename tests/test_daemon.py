import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import midi_pedald.daemon as daemon  # noqa: E402
from midi_pedald.config import Config, LogConfig, ObsConfig  # noqa: E402
from midi_pedald.daemon import Daemon, _build_sinks  # noqa: E402
from midi_pedald.mapping import Rule  # noqa: E402
from tests.fakes import FakeMido, FakeSink, start  # noqa: E402

# These tests never touch a real MIDI backend.
daemon.mido = FakeMido()


def cfg(rules=None):
    return Config(
        midi_port_substring="Scarlett",
        obs=ObsConfig(),
        log=LogConfig(),
        rules=rules or [Rule("start", "start_record")],
    )


def test_build_sinks_skips_a_failing_factory():
    def boom(_cfg):
        raise RuntimeError("no bus")

    sinks = _build_sinks(cfg(), {"good": lambda c: FakeSink(), "bad": boom})
    assert set(sinks) == {"good"}


def test_surviving_sink_still_receives_dispatch_after_a_sibling_fails_to_build():
    def boom(_cfg):
        raise RuntimeError("no bus")

    sinks = _build_sinks(cfg(), {"obs": lambda c: FakeSink(), "bad": boom})
    dae = Daemon(cfg(), sinks=sinks)
    dae._handle(start())
    assert sinks["obs"].calls == [("start_record", {})]


def test_handle_dispatches_to_the_obs_sink():
    s = FakeSink()
    Daemon(cfg(), sinks={"obs": s})._handle(start())
    assert s.calls == [("start_record", {})]


def test_handle_with_empty_registry_drops_without_crashing():
    Daemon(cfg(), sinks={})._handle(start())  # must not raise


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
