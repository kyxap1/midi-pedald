import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midi_pedald.config import ConfigError, OverlayConfig, _parse_sinks, rule_from_dict  # noqa: E402
from midi_pedald.overlay_sink import OverlaySink  # noqa: E402


class FakeProc:
    def __init__(self, raises=None):
        self.stdin = self
        self.closed = False
        self.killed = False
        self.alive = True
        self._raises = raises

    def close(self):
        self.closed = True

    def kill(self):
        self.killed = True
        self.alive = False

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        if self._raises is not None:
            raise self._raises
        self.alive = False
        return 0


class FakeSpawn:
    def __init__(self, raises=None, proc_raises=None):
        self.calls: list[list[str]] = []
        self.procs: list[FakeProc] = []
        self._raises = raises
        self._proc_raises = proc_raises

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self._raises is not None:
            raise self._raises
        p = FakeProc(raises=self._proc_raises)
        self.procs.append(p)
        return p


def sink(cfg=None, **spawn_kw):
    s = FakeSpawn(**spawn_kw)
    return OverlaySink(cfg or OverlayConfig(), spawn=s), s


def test_show_spawns_the_helper_with_the_configured_geometry():
    s, sp = sink(OverlayConfig(right_px=25, size_px=10, ring_px=2))
    s.dispatch("show")
    assert sp.calls[0][1:] == ["--size", "10", "--right", "25", "--ring", "2"]
    assert sp.calls[0][0].endswith("overlay-dot")


def test_top_is_left_to_the_helper_unless_configured():
    s, sp = sink(OverlayConfig(top_px=None))
    s.dispatch("show")
    assert "--top" not in sp.calls[0]

    s, sp = sink(OverlayConfig(top_px=4))
    s.dispatch("show")
    assert sp.calls[0][-2:] == ["--top", "4"]


def test_show_twice_does_not_stack_dots():
    s, sp = sink()
    s.dispatch("show")
    s.dispatch("show")
    assert len(sp.calls) == 1


def test_show_again_after_the_helper_died_respawns():
    s, sp = sink()
    s.dispatch("show")
    sp.procs[0].alive = False
    s.dispatch("show")
    assert len(sp.calls) == 2


def test_hide_closes_stdin_so_the_helper_exits():
    s, sp = sink()
    s.dispatch("show")
    s.dispatch("hide")
    assert sp.procs[0].closed


def test_hide_kills_a_helper_that_will_not_exit():
    s, sp = sink(proc_raises=subprocess.TimeoutExpired("overlay-dot", 2.0))
    s.dispatch("show")
    s.dispatch("hide")
    assert sp.procs[0].killed


def test_hide_without_show_is_a_no_op():
    s, _ = sink()
    s.dispatch("hide")


def test_a_helper_that_cannot_start_never_raises():
    s, sp = sink(raises=OSError("no such file"))
    s.dispatch("show")
    s.dispatch("hide")
    assert sp.calls != []


def test_unknown_method_spawns_nothing():
    s, sp = sink()
    s.dispatch("blink")
    assert sp.calls == []


def test_always_connected():
    s, _ = sink()
    assert s.connected is True and s.ensure_connected(0.0) is True


def test_show_rule_takes_no_params():
    try:
        rule_from_dict(
            {"event": "start", "action": "overlay.show", "params": {"file": "x"}}, 0, {"overlay"}
        )
    except ConfigError as e:
        assert "file" in str(e)
    else:
        raise AssertionError("expected ConfigError")


def test_valid_overlay_rules():
    for method in ("show", "hide"):
        r = rule_from_dict({"event": "start", "action": f"overlay.{method}"}, 0, {"overlay"})
        assert r.sink == "overlay" and r.method == method


def test_sink_block_defaults():
    assert _parse_sinks({"sinks": {"overlay": {}}})["overlay"] == OverlayConfig(
        right_px=25, top_px=None, size_px=10, ring_px=2
    )


def test_a_ringless_dot_is_allowed():
    assert _parse_sinks({"sinks": {"overlay": {"ring_px": 0}}})["overlay"].ring_px == 0


def test_negative_offset_rejected():
    try:
        _parse_sinks({"sinks": {"overlay": {"right_px": -1}}})
    except ConfigError as e:
        assert "right_px" in str(e)
    else:
        raise AssertionError("expected ConfigError")


def test_zero_size_rejected():
    try:
        _parse_sinks({"sinks": {"overlay": {"size_px": 0}}})
    except ConfigError as e:
        assert "size_px" in str(e)
    else:
        raise AssertionError("expected ConfigError")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
