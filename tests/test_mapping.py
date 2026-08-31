import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midi_pedald.mapping import Rule, RuleTable, to_event  # noqa: E402
from tests.fakes import cc, clock, pc, start, stop  # noqa: E402


def table(*rules):
    return RuleTable(list(rules))


def test_program_change_exact():
    t = table(Rule("program_change", "split_record_file", number=5))
    assert t.decide(to_event(pc(5)), 0.0).action == "split_record_file"
    assert t.decide(to_event(pc(6)), 1.0).action is None


def test_program_change_range():
    t = table(Rule("program_change", "split_record_file", number_range=(0, 98)))
    assert t.decide(to_event(pc(0)), 0.0).action == "split_record_file"
    assert t.decide(to_event(pc(98)), 10.0).action == "split_record_file"
    assert t.decide(to_event(pc(99)), 20.0).action is None


def test_control_change_value_range():
    t = table(Rule("control_change", "save_replay_buffer", number=80, value_range=(64, 127)))
    assert t.decide(to_event(cc(80, 127)), 0.0).action == "save_replay_buffer"
    assert t.decide(to_event(cc(80, 10)), 1.0).action is None
    assert t.decide(to_event(cc(81, 127)), 2.0).action is None


def test_start_stop_events():
    t = table(
        Rule("start", "start_record"),
        Rule("stop", "stop_record"),
    )
    assert t.decide(to_event(start()), 0.0).action == "start_record"
    assert t.decide(to_event(stop()), 1.0).action == "stop_record"


def test_first_match_wins():
    t = table(
        Rule("program_change", "noop", number_range=(0, 10)),
        Rule("program_change", "split_record_file", number=5),
    )
    d = t.decide(to_event(pc(5)), 0.0)
    assert d.action == "noop" and d.rule_index == 0


def test_debounce_blocks_then_allows():
    t = table(Rule("start", "start_record", debounce_ms=300))
    assert t.decide(to_event(start()), 0.0).action == "start_record"
    assert t.decide(to_event(start()), 0.2).action is None  # 200ms < 300ms
    assert t.decide(to_event(start()), 0.35).action == "start_record"  # 350ms elapsed


def test_debounce_is_per_rule():
    t = table(
        Rule("start", "start_record", debounce_ms=1000),
        Rule("stop", "stop_record", debounce_ms=1000),
    )
    assert t.decide(to_event(start()), 0.0).action == "start_record"
    assert t.decide(to_event(stop()), 0.1).action == "stop_record"  # different rule, not debounced


def test_clock_maps_to_other_and_never_matches():
    ev = to_event(clock())
    assert ev.kind == "other"
    t = table(Rule("start", "start_record"), Rule("stop", "stop_record"))
    assert t.decide(ev, 0.0).action is None


def test_no_rule_matched_reason():
    t = table(Rule("start", "start_record"))
    assert t.decide(to_event(stop()), 0.0).reason == "no rule matched"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
