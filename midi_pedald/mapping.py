"""MIDI-event -> OBS-action mapping: parsing, rule matching, per-rule debounce.

Deliberately free of third-party imports so it can be unit-tested with plain
`python3` and duck-typed fake messages.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Dropped by the daemon before this module ever sees them; listed here only so
# the daemon and the monitor agree on what "realtime spam" means.
REALTIME_DROP = ("clock", "active_sensing")

EVENTS = ("start", "stop", "continue", "program_change", "control_change")


@dataclass(frozen=True)
class MidiEvent:
    kind: str
    channel: int | None = None
    number: int | None = None  # program_change: program; control_change: controller
    value: int | None = None  # control_change: value
    raw: tuple[int, ...] = ()

    def __str__(self) -> str:
        parts = [f"kind={self.kind}"]
        if self.channel is not None:
            parts.append(f"ch={self.channel + 1}")
        if self.number is not None:
            parts.append(f"num={self.number}")
        if self.value is not None:
            parts.append(f"val={self.value}")
        parts.append("raw=[" + " ".join(f"{b:02X}" for b in self.raw) + "]")
        return " ".join(parts)


def to_event(msg) -> MidiEvent:
    """Convert a mido-like message (duck-typed) into a MidiEvent."""
    try:
        raw = tuple(msg.bytes())
    except Exception:
        raw = ()
    ch = getattr(msg, "channel", None)
    t = msg.type
    if t == "program_change":
        return MidiEvent("program_change", ch, getattr(msg, "program", None), None, raw)
    if t == "control_change":
        return MidiEvent(
            "control_change", ch, getattr(msg, "control", None), getattr(msg, "value", None), raw
        )
    if t in ("start", "stop", "continue"):
        return MidiEvent(t, raw=raw)
    return MidiEvent("other", ch, raw=raw)


@dataclass
class Rule:
    event: str
    action: str  # "sink.method" — validated at config load
    debounce_ms: int = 300
    number: int | None = None  # exact program (PC) or controller (CC) number
    number_range: tuple[int, int] | None = None  # inclusive PC range
    value_range: tuple[int, int] | None = None  # inclusive CC value range
    params: dict = field(default_factory=dict)  # kwargs passed to the sink method

    @property
    def sink(self) -> str:
        return self.action.split(".", 1)[0]

    @property
    def method(self) -> str:
        return self.action.split(".", 1)[1]

    def matches(self, ev: MidiEvent) -> bool:
        if ev.kind != self.event:
            return False
        if self.event == "program_change":
            return _in_selection(ev.number, self.number, self.number_range)
        if self.event == "control_change":
            if self.number is not None and ev.number != self.number:
                return False
            if self.value_range is not None:
                lo, hi = self.value_range
                return ev.value is not None and lo <= ev.value <= hi
            return True
        return True  # start / stop / continue carry no selector


def _in_selection(actual, exact, rng) -> bool:
    if actual is None:
        return False
    if exact is not None:
        return actual == exact
    if rng is not None:
        return rng[0] <= actual <= rng[1]
    return True


@dataclass
class Decision:
    sink: str
    method: str
    params: dict
    rule_index: int
    reason: str


class RuleTable:
    """Every matching rule fires, in file order. Debounce is tracked per rule
    index, so one rule firing never debounces another."""

    def __init__(self, rules: list[Rule]):
        self.rules = rules
        self._last_fire: dict[int, float] = {}

    def decide_all(self, ev: MidiEvent, now: float) -> list[Decision]:
        out: list[Decision] = []
        for i, rule in enumerate(self.rules):
            if not rule.matches(ev):
                continue
            last = self._last_fire.get(i)
            if last is not None and (now - last) * 1000.0 < rule.debounce_ms:
                continue
            self._last_fire[i] = now
            out.append(Decision(rule.sink, rule.method, dict(rule.params), i, f"rule {i} matched"))
        return out
