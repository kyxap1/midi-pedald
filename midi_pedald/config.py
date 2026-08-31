"""YAML config loading and validation. `yaml` is imported inside `load()` so the
rule-building helpers stay importable without PyYAML."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mapping import EVENTS, Rule
from .midi_sink import MIDI_OUT_METHODS
from .obs_sink import OBS_METHODS


class ConfigError(Exception):
    pass


@dataclass
class ObsConfig:
    host: str = "localhost"
    port: int = 4455
    password: str = ""


@dataclass
class MidiOutConfig:
    port_substring: str


# Sink type -> the method names a rule may name as "<sink>.<method>".
SINK_METHODS: dict[str, frozenset] = {"obs": OBS_METHODS, "midi_out": MIDI_OUT_METHODS}

# "<sink>.<method>" -> accepted param names / the subset that is required.
# Absent entry means the method takes no params.
SINK_METHOD_PARAMS: dict[str, set] = {"midi_out.cc_sequence": {"cc", "gap_ms"}}
SINK_METHOD_REQUIRED: dict[str, set] = {"midi_out.cc_sequence": {"cc"}}


_DEFAULT_LOG_FILE = "~/Library/Logs/midi-pedald/midi-pedald.log"


@dataclass
class LogConfig:
    level: str = "INFO"
    file: str | None = _DEFAULT_LOG_FILE
    max_bytes: int = 1_048_576
    backup_count: int = 3


@dataclass
class Config:
    midi_port_substring: str
    sinks: dict[str, object]
    log: LogConfig
    rules: list[Rule]


def _pair(value, where: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(x, int) for x in value):
        raise ConfigError(f"{where} must be a [lo, hi] list of two integers")
    lo, hi = value
    if lo > hi:
        raise ConfigError(f"{where} has lo > hi")
    return (lo, hi)


def _validate_action(action, params: dict, declared_sinks, idx: int) -> None:
    if not isinstance(action, str) or "." not in action:
        raise ConfigError(f"rules[{idx}].action {action!r} must be 'sink.method'")
    sink_name, method = action.split(".", 1)
    if sink_name not in declared_sinks:
        raise ConfigError(
            f"rules[{idx}].action names sink {sink_name!r} but there is no sinks.{sink_name} block"
        )
    methods = SINK_METHODS.get(sink_name)
    if methods is None:
        raise ConfigError(f"rules[{idx}].action names unknown sink type {sink_name!r}")
    if method not in methods:
        raise ConfigError(
            f"rules[{idx}].action {action!r}: sink {sink_name!r} has no method {method!r}"
        )
    allowed = SINK_METHOD_PARAMS.get(action, set())
    extra = set(params) - allowed
    if extra:
        raise ConfigError(
            f"rules[{idx}].params has keys {sorted(extra)} not accepted by {action}"
        )
    missing = SINK_METHOD_REQUIRED.get(action, set()) - set(params)
    if missing:
        raise ConfigError(f"rules[{idx}].params is missing {sorted(missing)} required by {action}")


def rule_from_dict(d: dict, idx: int, declared_sinks) -> Rule:
    if not isinstance(d, dict):
        raise ConfigError(f"rules[{idx}] must be a mapping")
    event = d.get("event")
    if event not in EVENTS:
        raise ConfigError(f"rules[{idx}].event {event!r} not one of {list(EVENTS)}")
    params = d.get("params") or {}
    if not isinstance(params, dict):
        raise ConfigError(f"rules[{idx}].params must be a mapping")
    _validate_action(d.get("action"), params, declared_sinks, idx)
    number = d.get("number")
    if number is not None and not isinstance(number, int):
        raise ConfigError(f"rules[{idx}].number must be an integer")
    debounce = d.get("debounce_ms", 300)
    if not isinstance(debounce, int) or debounce < 0:
        raise ConfigError(f"rules[{idx}].debounce_ms must be a non-negative integer")
    if event == "control_change" and number is None and "value_range" not in d:
        raise ConfigError(f"rules[{idx}] control_change needs a number and/or value_range")
    return Rule(
        event=event,
        action=d["action"],
        debounce_ms=debounce,
        number=number,
        number_range=_pair(d.get("range"), f"rules[{idx}].range"),
        value_range=_pair(d.get("value_range"), f"rules[{idx}].value_range"),
        params=params,
    )


def _parse_sinks(data: dict) -> dict[str, object]:
    raw = data.get("sinks")
    if not isinstance(raw, dict) or not raw:
        raise ConfigError("sinks must be a non-empty mapping")
    out: dict[str, object] = {}
    for name, sc in raw.items():
        sc = sc or {}
        if not isinstance(sc, dict):
            raise ConfigError(f"sinks.{name} must be a mapping")
        if name == "obs":
            out["obs"] = ObsConfig(
                host=str(sc.get("host", "localhost")),
                port=int(sc.get("port", 4455)),
                password=str(sc.get("password", "") or ""),
            )
        elif name == "midi_out":
            ps = sc.get("port_substring")
            if not ps or not isinstance(ps, str):
                raise ConfigError("sinks.midi_out.port_substring is required and must be a string")
            out["midi_out"] = MidiOutConfig(port_substring=ps)
        else:
            raise ConfigError(f"unknown sink {name!r} (known: {sorted(SINK_METHODS)})")
    return out


def load(path: str | Path) -> Config:
    import yaml

    p = Path(path).expanduser()
    try:
        raw = p.read_text()
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {p}")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {p}: {e}")
    if not isinstance(data, dict):
        raise ConfigError("top-level config must be a mapping")

    midi = data.get("midi") or {}
    substring = midi.get("port_substring")
    if not substring or not isinstance(substring, str):
        raise ConfigError("midi.port_substring is required and must be a string")

    sinks = _parse_sinks(data)

    lg = data.get("logging") or {}
    log = LogConfig(
        level=str(lg.get("level", "INFO")).upper(),
        file=lg.get("file", _DEFAULT_LOG_FILE),
        max_bytes=int(lg.get("max_bytes", 1_048_576)),
        backup_count=int(lg.get("backup_count", 3)),
    )

    rules_raw = data.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ConfigError("rules must be a non-empty list")
    rules = [rule_from_dict(d, i, set(sinks)) for i, d in enumerate(rules_raw)]

    return Config(midi_port_substring=substring, sinks=sinks, log=log, rules=rules)
