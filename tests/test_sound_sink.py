import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midi_pedald.config import ConfigError, SoundConfig, _parse_sinks, rule_from_dict  # noqa: E402
from midi_pedald.sound_sink import SoundSink, resolve_sound  # noqa: E402


class FakeRunner:
    def __init__(self, returncode=0, raises=None):
        self.calls: list[list[str]] = []
        self._rc = returncode
        self._raises = raises

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self._raises is not None:
            raise self._raises
        return types.SimpleNamespace(returncode=self._rc, stderr=b"")


def sink(volume=1.0, **runner_kw):
    r = FakeRunner(**runner_kw)
    return SoundSink(SoundConfig(volume=volume), runner=r), r


def test_bare_name_resolves_to_a_system_sound():
    assert resolve_sound("Tink") == Path("/System/Library/Sounds/Tink.aiff")


def test_path_is_used_as_given():
    assert resolve_sound("~/sounds/blip.wav") == Path.home() / "sounds/blip.wav"


def test_play_runs_afplay_with_the_configured_volume_and_cap():
    s, r = sink(volume=0.4)
    s.dispatch("play", file="Tink")
    assert r.calls == [
        ["/usr/bin/afplay", "-v", "0.4", "-t", "0.150", "/System/Library/Sounds/Tink.aiff"]
    ]


def test_unknown_method_plays_nothing():
    s, r = sink()
    s.dispatch("speak", file="Tink")
    assert r.calls == []


def test_afplay_blowing_up_never_raises():
    s, r = sink(raises=OSError("no such binary"))
    s.dispatch("play", file="Tink")
    assert r.calls != []  # tried, swallowed the error


def test_afplay_nonzero_exit_never_raises():
    s, _ = sink(returncode=1)
    s.dispatch("play", file="Missing")


def test_always_connected():
    s, _ = sink()
    assert s.connected is True and s.ensure_connected(0.0) is True


def test_play_rule_needs_a_file_param():
    try:
        rule_from_dict({"event": "start", "action": "sound.play"}, 0, {"sound"})
    except ConfigError as e:
        assert "file" in str(e)
    else:
        raise AssertionError("expected ConfigError")


def test_play_rule_rejects_unknown_params():
    try:
        rule_from_dict(
            {"event": "start", "action": "sound.play", "params": {"file": "Tink", "gap_ms": 5}},
            0,
            {"sound"},
        )
    except ConfigError as e:
        assert "gap_ms" in str(e)
    else:
        raise AssertionError("expected ConfigError")


def test_valid_play_rule():
    r = rule_from_dict(
        {"event": "start", "action": "sound.play", "params": {"file": "Tink"}}, 0, {"sound"}
    )
    assert r.sink == "sound" and r.method == "play" and r.params == {"file": "Tink"}


def test_sink_block_defaults_to_full_volume():
    assert _parse_sinks({"sinks": {"sound": {}}})["sound"] == SoundConfig(volume=1.0, max_ms=150)


def test_max_ms_is_configurable():
    s, r = sink(volume=1.0)
    s.max_ms = 40
    s.dispatch("play", file="Tink")
    assert "0.040" in r.calls[0]


def test_zero_volume_rejected():
    try:
        _parse_sinks({"sinks": {"sound": {"volume": 0}}})
    except ConfigError as e:
        assert "volume" in str(e)
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
