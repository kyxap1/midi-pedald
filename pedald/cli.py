from __future__ import annotations

import argparse
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__

_FMT = "%(asctime)s %(levelname)-7s %(message)s"
_DEFAULT_CONFIG = "~/Library/Application Support/pedald/config.yaml"


def _resolve_config(arg: str | None) -> Path:
    """--config default lands in Application Support; an explicit path (relative
    included) is used verbatim."""
    return Path(arg or _DEFAULT_CONFIG).expanduser()


def _setup_logging(cfg) -> None:
    root = logging.getLogger("pedald")
    root.setLevel(cfg.level)
    root.propagate = False
    fmt = logging.Formatter(_FMT)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)
    if cfg.file:
        path = Path(cfg.file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        rot = RotatingFileHandler(path, maxBytes=cfg.max_bytes, backupCount=cfg.backup_count)
        rot.setFormatter(fmt)
        root.addHandler(rot)


def _print_msg(msg) -> None:
    raw = " ".join(f"{b:02X}" for b in msg.bytes())
    ts = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
    ch = getattr(msg, "channel", None)
    ch_s = f"ch{ch + 1}" if ch is not None else "-"
    detail = " ".join(
        f"{a}={getattr(msg, a)}"
        for a in ("program", "control", "value", "note", "velocity", "pitch")
        if hasattr(msg, a)
    )
    print(f"{ts}  {raw:<11}  {msg.type:<15} {ch_s:<5} {detail}")


def _monitor(port_sub: str | None, show_clock: bool) -> int:
    import mido

    names = mido.get_input_names()
    print("Available MIDI inputs:")
    for n in names:
        print(f"  - {n}")
    if not names:
        print("  (none)")
        return 1

    if port_sub:
        target = next((n for n in names if port_sub.lower() in n.lower()), None)
        if target is None:
            print(f"\nno input matches {port_sub!r}")
            return 1
    else:
        target = names[0]

    print(f"\nMonitoring: {target}   (Ctrl-C to stop)\n")
    drop = set() if show_clock else {"clock", "active_sensing"}
    port = mido.open_input(target)
    if show_clock:
        # mido leaves active sensing filtered at the rtmidi driver; re-enable it.
        try:
            port._rt.ignore_types(False, False, False)
        except Exception:
            pass
    try:
        with port:
            for msg in port:
                if msg.type in drop:
                    continue
                _print_msg(msg)
    except KeyboardInterrupt:
        print()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pedald", description="MIDI pedal -> multi-sink daemon")
    p.add_argument("--monitor", action="store_true", help="print incoming MIDI, then exit")
    p.add_argument("--port", help="MIDI input name substring (monitor mode)")
    p.add_argument(
        "--show-clock", action="store_true", help="do not filter MIDI Clock / Active Sensing"
    )
    p.add_argument("--config", default=None, help="YAML config path (daemon mode)")
    p.add_argument("--version", action="version", version=f"pedald {__version__}")
    args = p.parse_args(argv)

    if args.monitor:
        return _monitor(args.port, args.show_clock)

    from .config import ConfigError, load
    from .daemon import Daemon

    try:
        cfg = load(_resolve_config(args.config))
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    _setup_logging(cfg.log)
    Daemon(cfg).run()
    return 0
