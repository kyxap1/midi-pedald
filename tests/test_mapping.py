import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midi_pedald.mapping import Rule, RuleTable, to_event  # noqa: E402
from tests.fakes import cc, clock, pc, start, stop  # noqa: E402


def table(*rules):
    return RuleTable(list(rules))


def actions(decisions):
    return [(d.sink, d.method) for d in decisions]


def test_program_change_exact():
    t = table(Rule("program_change", "obs.split_record_file", number=5))
    assert actions(t.decide_all(to_event(pc(5)), 0.0)) == [("obs", "split_record_file")]
    assert t.decide_all(to_event(pc(6)), 1.0) == []


def test_program_change_range():
    t = table(Rule("program_change", "obs.split_record_file", number_range=(0, 98)))
    assert t.decide_all(to_event(pc(0)), 0.0)
    assert t.decide_all(to_event(pc(98)), 10.0)
    assert t.decide_all(to_event(pc(99)), 20.0) == []


def test_control_change_value_range():
    t = table(Rule("control_change", "obs.save_replay_buffer", number=80, value_range=(64, 127)))
    assert t.decide_all(to_event(cc(80, 127)), 0.0)
    assert t.decide_all(to_event(cc(80, 10)), 1.0) == []
    assert t.decide_all(to_event(cc(81, 127)), 2.0) == []


def test_start_stop_events():
    t = table(Rule("start", "obs.start_record"), Rule("stop", "obs.stop_record"))
    assert actions(t.decide_all(to_event(start()), 0.0)) == [("obs", "start_record")]
    assert actions(t.decide_all(to_event(stop()), 1.0)) == [("obs", "stop_record")]


def test_every_matching_rule_fires_in_file_order():
    t = table(
        Rule("start", "obs.start_record"),
        Rule("start", "midi_out.cc_sequence", params={"cc": [[22, 127]]}),
    )
    d = t.decide_all(to_event(start()), 0.0)
    assert actions(d) == [("obs", "start_record"), ("midi_out", "cc_sequence")]
    assert d[1].params == {"cc": [[22, 127]]}


def test_two_rules_on_the_same_sink_both_fire():
    t = table(
        Rule("start", "obs.start_record"),
        Rule("start", "obs.split_record_file"),
    )
    assert actions(t.decide_all(to_event(start()), 0.0)) == [
        ("obs", "start_record"),
        ("obs", "split_record_file"),
    ]


def test_debounce_under_multi_fire_drops_only_the_debounced_rule():
    t = table(
        Rule("start", "obs.start_record", debounce_ms=1000),
        Rule("start", "midi_out.cc_sequence", debounce_ms=0, params={"cc": []}),
    )
    assert len(t.decide_all(to_event(start()), 0.0)) == 2
    d = t.decide_all(to_event(start()), 0.1)  # 100ms: rule 0 debounced, rule 1 not
    assert actions(d) == [("midi_out", "cc_sequence")]


def test_debounce_is_per_rule_not_per_event():
    t = table(
        Rule("start", "obs.start_record", debounce_ms=1000),
        Rule("stop", "obs.stop_record", debounce_ms=1000),
    )
    assert t.decide_all(to_event(start()), 0.0)
    assert t.decide_all(to_event(stop()), 0.1)  # different rule, not debounced


def test_debounce_blocks_then_allows():
    t = table(Rule("start", "obs.start_record", debounce_ms=300))
    assert t.decide_all(to_event(start()), 0.0)
    assert t.decide_all(to_event(start()), 0.2) == []
    assert t.decide_all(to_event(start()), 0.35)


def test_clock_maps_to_other_and_never_matches():
    ev = to_event(clock())
    assert ev.kind == "other"
    t = table(Rule("start", "obs.start_record"), Rule("stop", "obs.stop_record"))
    assert t.decide_all(ev, 0.0) == []


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
