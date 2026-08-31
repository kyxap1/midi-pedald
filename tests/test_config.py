import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midi_pedald.config import ConfigError, load, rule_from_dict  # noqa: E402

SINKS = {"obs"}


def mk(d, sinks=SINKS):
    return rule_from_dict(d, 0, sinks)


def expect_error(d, needle, sinks=SINKS):
    try:
        rule_from_dict(d, 0, sinks)
    except ConfigError as e:
        assert needle in str(e), f"{needle!r} not in {e!r}"
    else:
        raise AssertionError(f"expected ConfigError containing {needle!r}")


def test_valid_start_rule():
    r = mk({"event": "start", "action": "obs.start_record"})
    assert r.event == "start" and r.action == "obs.start_record" and r.debounce_ms == 300
    assert r.sink == "obs" and r.method == "start_record"


def test_valid_pc_range_rule():
    r = mk({"event": "program_change", "action": "obs.split_record_file", "range": [0, 98]})
    assert r.number_range == (0, 98)


def test_unknown_event_rejected():
    expect_error({"event": "panic", "action": "obs.start_record"}, "event")


def test_unknown_method_rejected():
    expect_error({"event": "start", "action": "obs.explode"}, "explode")


def test_bare_action_without_sink_prefix_rejected():
    expect_error({"event": "start", "action": "start_record"}, "sink.method")


def test_action_naming_undeclared_sink_rejected():
    expect_error({"event": "start", "action": "midi_out.cc_sequence", "params": {"cc": []}}, "midi_out")


def test_midi_out_cc_sequence_valid_with_params():
    r = rule_from_dict(
        {"event": "start", "action": "midi_out.cc_sequence",
         "params": {"cc": [[22, 127]], "gap_ms": 50}},
        0,
        {"obs", "midi_out"},
    )
    assert r.sink == "midi_out" and r.method == "cc_sequence"
    assert r.params == {"cc": [[22, 127]], "gap_ms": 50}


def test_cc_sequence_missing_required_cc_rejected():
    expect_error(
        {"event": "start", "action": "midi_out.cc_sequence", "params": {"gap_ms": 5}},
        "cc",
        sinks={"obs", "midi_out"},
    )


def test_cc_sequence_unknown_param_rejected():
    expect_error(
        {"event": "start", "action": "midi_out.cc_sequence", "params": {"cc": [], "wat": 1}},
        "wat",
        sinks={"obs", "midi_out"},
    )


def test_params_on_paramless_method_rejected():
    expect_error({"event": "start", "action": "obs.start_record", "params": {"gap_ms": 5}}, "gap_ms")


def test_bad_range_rejected():
    expect_error({"event": "program_change", "action": "obs.start_record", "range": [1, 2, 3]}, "lo, hi")


def test_inverted_range_rejected():
    expect_error({"event": "program_change", "action": "obs.start_record", "range": [9, 1]}, "lo > hi")


def test_negative_debounce_rejected():
    expect_error({"event": "start", "action": "obs.start_record", "debounce_ms": -1}, "debounce_ms")


def test_cc_without_selector_rejected():
    expect_error({"event": "control_change", "action": "obs.start_record"}, "number and/or value_range")


def test_example_config_loads_clean():
    cfg = load(Path(__file__).resolve().parents[1] / "config.example.yaml")
    assert cfg.midi_port_substring
    assert "obs" in cfg.sinks
    assert cfg.rules


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
