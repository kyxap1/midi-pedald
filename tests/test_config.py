import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midiobs.config import ConfigError, rule_from_dict  # noqa: E402


def expect_error(d, needle):
    try:
        rule_from_dict(d, 0)
    except ConfigError as e:
        assert needle in str(e), f"{needle!r} not in {e!r}"
    else:
        raise AssertionError(f"expected ConfigError containing {needle!r}")


def test_valid_start_rule():
    r = rule_from_dict({"event": "start", "action": "start_record"}, 0)
    assert r.event == "start" and r.action == "start_record" and r.debounce_ms == 300


def test_valid_pc_range_rule():
    r = rule_from_dict({"event": "program_change", "action": "noop", "range": [0, 98]}, 0)
    assert r.number_range == (0, 98)


def test_unknown_event_rejected():
    expect_error({"event": "panic", "action": "noop"}, "event")


def test_unknown_action_rejected():
    expect_error({"event": "start", "action": "explode"}, "action")


def test_bad_range_rejected():
    expect_error({"event": "program_change", "action": "noop", "range": [1, 2, 3]}, "lo, hi")


def test_inverted_range_rejected():
    expect_error({"event": "program_change", "action": "noop", "range": [9, 1]}, "lo > hi")


def test_negative_debounce_rejected():
    expect_error({"event": "start", "action": "noop", "debounce_ms": -1}, "debounce_ms")


def test_cc_without_selector_rejected():
    expect_error({"event": "control_change", "action": "noop"}, "number and/or value_range")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
