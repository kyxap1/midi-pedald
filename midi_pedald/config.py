"""YAML config loading and validation. `yaml` is imported inside `load()` so the
rule-building helpers stay importable without PyYAML."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mapping import ACTIONS, EVENTS, Rule


class ConfigError(Exception):
    pass


@dataclass
class ObsConfig:
    host: str = "localhost"
    port: int = 4455
    password: str = ""


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
    obs: ObsConfig
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


def rule_from_dict(d: dict, idx: int) -> Rule:
    if not isinstance(d, dict):
        raise ConfigError(f"rules[{idx}] must be a mapping")
    event = d.get("event")
    if event not in EVENTS:
        raise ConfigError(f"rules[{idx}].event {event!r} not one of {list(EVENTS)}")
    action = d.get("action")
    if action not in ACTIONS:
        raise ConfigError(f"rules[{idx}].action {action!r} not one of {list(ACTIONS)}")
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
        action=action,
        debounce_ms=debounce,
        number=number,
        number_range=_pair(d.get("range"), f"rules[{idx}].range"),
        value_range=_pair(d.get("value_range"), f"rules[{idx}].value_range"),
    )


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

    o = data.get("obs") or {}
    obs = ObsConfig(
        host=str(o.get("host", "localhost")),
        port=int(o.get("port", 4455)),
        password=str(o.get("password", "") or ""),
    )

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
    rules = [rule_from_dict(d, i) for i, d in enumerate(rules_raw)]

    return Config(midi_port_substring=substring, obs=obs, log=log, rules=rules)
