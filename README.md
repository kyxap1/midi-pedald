# midi-pedald

A macOS daemon that listens on one MIDI input and drives **N independent sinks**
from it. Built for a Boss RC-5 looper wired through a Focusrite Scarlett: one
pedal press starts an OBS recording *and* a Waveform Free take at the same time.

Each sink reconnects on its own. OBS not running, Waveform closed, the IAC bus
missing, the sound card unplugged — any sink can be absent or flapping without
touching the others, and the daemon never exits.

It reacts to MIDI **Start** (`0xFA`), **Stop** (`0xFC`), **Continue** (`0xFB`),
**Program Change** and **Control Change**. **MIDI Clock** (`0xF8`) feeds a BPM
meter (log-only) and is then dropped before any rule logic.

## Requirements

- Apple silicon (arm64) macOS. No Python, no Xcode CLT — the `.pkg` is
  self-contained.
- OBS Studio 28+ with obs-websocket enabled (*Tools → WebSocket Server
  Settings → Enable*), only if you use an `obs.*` rule. OBS **30.2+** for
  `obs.split_record_file`.
- An IAC bus, only if you use a `midi_out.*` rule — see
  [Wiring Waveform](#wiring-waveform-free).

## Install

Download `midi-pedald-<version>.pkg` from the
[latest release](../../releases/latest) and open it. It installs into your home
folder — no admin password.

The pkg is **not signed** (signing is out of scope for now), so Gatekeeper
blocks the first open. Either:

- Right-click the pkg → **Open** → **Open** in the dialog, or
- **System Settings → Privacy & Security**, scroll down, **Open Anyway**, or
- `xattr -dr com.apple.quarantine ~/Downloads/midi-pedald-*.pkg` then open it.

The installer:

- puts the daemon at `~/Library/Application Support/midi-pedald/bin/`
- writes `~/Library/Application Support/midi-pedald/config.yaml` from the
  bundled example **only if you don't already have one** (upgrades keep yours)
- loads a launchd agent (`pro.kyxap.midi-pedald`, `RunAtLoad` + `KeepAlive`)

Then edit the config (at minimum `midi.port_substring`, and `sinks.obs.password`
if you use OBS) and restart:

```sh
launchctl kickstart -k gui/$(id -u)/pro.kyxap.midi-pedald
```

### Everything it owns

| | |
|---|---|
| Bundle | `~/Library/Application Support/midi-pedald/bin/` |
| Config | `~/Library/Application Support/midi-pedald/config.yaml` |
| Logs | `~/Library/Logs/midi-pedald/` |
| Agent | `~/Library/LaunchAgents/pro.kyxap.midi-pedald.plist` |

`./uninstall.sh` removes the agent and bundle and asks before deleting config
and logs.

## Finding your MIDI port name

Run the frozen binary in the foreground:

```sh
~/Library/Application\ Support/midi-pedald/bin/midi-pedald --monitor
```

This prints every MIDI input, then every incoming message on the first one (or
on `--port <substring>`): raw bytes, parsed type, channel, values. Clock and
Active Sensing are hidden; add `--show-clock` to see them.

```
Available MIDI inputs:
  - Scarlett 18i16 USB
  - IAC Driver Bus 1

Monitoring: Scarlett 18i16 USB   (Ctrl-C to stop)

14:22:07.031  FA           start           -
14:22:19.884  C0 04        program_change  ch1   program=4
14:22:31.512  FC           stop            -
```

Put a stable substring of that name (`"Scarlett"`) into `midi.port_substring`.
Matching is case-insensitive and re-scanned every 2 seconds.

## Config

YAML at `~/Library/Application Support/midi-pedald/config.yaml`. See
`config.example.yaml` for a full working file.

```yaml
midi:
  port_substring: "Scarlett"

sinks:                       # one block per sink; a sink with no block is
  obs:                       # disabled, and a rule naming it is a config error
    host: localhost
    port: 4455
    password: ""
  midi_out:
    port_substring: "IAC"

bpm:
  enabled: true
  window_ticks: 96           # 96 = one 4/4 bar
  tolerance: 1.5             # BPM dead-band
  confirm_windows: 2         # windows a new tempo must hold before the latch moves

logging:
  level: INFO                # DEBUG = every MIDI event and every rule decision
  file: "~/Library/Logs/midi-pedald/midi-pedald.log"
  max_bytes: 1048576
  backup_count: 3

rules:
  - { event: start, action: obs.start_record, debounce_ms: 500 }
  - { event: start, action: midi_out.cc_sequence, debounce_ms: 500,
      params: { cc: [[22, 127], [20, 127]], gap_ms: 50 } }
  - { event: stop,  action: obs.stop_record, debounce_ms: 500 }
  - { event: stop,  action: midi_out.cc_sequence, debounce_ms: 500,
      params: { cc: [[21, 127], [22, 127]], gap_ms: 50 } }
```

### Rules

**Every** matching rule fires, in file order. Each rule:

| key           | meaning |
|---------------|---------|
| `event`       | `start` \| `stop` \| `continue` \| `program_change` \| `control_change` |
| `action`      | `"<sink>.<method>"` — see below |
| `debounce_ms` | ignore repeats of *this rule* within this window (default `300`) |
| `number`      | exact Program Change program, or exact CC controller number |
| `range`       | `[lo, hi]` inclusive Program Change range |
| `value_range` | `[lo, hi]` inclusive CC value range |
| `params`      | kwargs for the sink method (only `midi_out.cc_sequence` takes any) |

`number` / `range` / `value_range` are **raw wire values, 0–127**. The RC-5
shows memory numbers from 1, so its "memory 1" is Program Change `0` on the wire
— confirm with `--monitor`.

| action | effect |
|---|---|
| `obs.start_record` / `obs.stop_record` | start / stop recording (state-checked, so a doubled press never errors) |
| `obs.toggle_record` | toggle recording |
| `obs.split_record_file` | close the file, start a new one (OBS 30.2+) |
| `obs.save_replay_buffer` / `obs.start_replay_buffer` / `obs.stop_replay_buffer` | replay buffer |
| `midi_out.cc_sequence` | send CCs in order; `params: { cc: [[num, val], ...], gap_ms: N }` |

A `cc_sequence` `gap_ms` blocks the dispatch loop for its duration, so put
`obs.*` rules **above** `midi_out.*` rules. The MIDI callback only enqueues, so
nothing is dropped while the loop is busy.

Debounce is per rule: firing one rule never debounces another on the same event.
That per-rule debounce is what still protects against a doubled pedal press.

## Wiring Waveform Free

Waveform Free 14 has no MIDI Clock reception and no Ableton Link (Pro only), so
tempo cannot be delivered — `bpm` in the config is **log-only**. What Free *does*
accept is a Custom Control Surface over MIDI, learned to CC.

1. **Audio MIDI Setup → MIDI Studio** → double-click **IAC Driver** → tick
   *Device is online*, make sure **Bus 1** exists.
2. Waveform → **Settings → Control Surfaces → Create New Custom Control
   Surface**. Protocol **MIDI**, **Input Device = IAC Driver Bus 1**. Tick
   **Hide MIDI Input Device** so the CCs don't leak into the audio path and get
   recorded into clips.
3. **Edit Control Mappings** → for each row (Record, Stop, Rewind), click
   *Learn*, then trigger the matching pedal event once so midi-pedald sends the CC.
   The example config uses CC 20 = record, 21 = stop, 22 = rewind — any numbers
   work as long as config and Waveform agree.

If the learned mapping ever drifts (project reload, IAC renumbering, device
order change) midi-pedald keeps sending into the void — there's no feedback channel
from Free. Re-learn the rows.

## Logs

- `~/Library/Logs/midi-pedald/midi-pedald.log`, rotated by size
- launchd stdout/stderr at `~/Library/Logs/midi-pedald/launchd.{out,err}.log`

`INFO` covers connection events, recording state changes, and BPM latch moves.
`DEBUG` adds every accepted MIDI event and every rule decision.

## Nothing is coming through?

1. **`--monitor` shows no inputs.** The Scarlett isn't presenting a MIDI port —
   check the USB cable and *Audio MIDI Setup → MIDI Studio*.
2. **Port listed but nothing on pedal press.** The MIDI chain isn't reaching the
   Scarlett IN. Check each pedal's THRU/OUT. On the RC-5: `SETUP → MIDI`,
   `CLOCK OUT = ON`, `PC OUT = ON`.
3. **Messages in `--monitor` but the daemon does nothing.** Set
   `logging.level: DEBUG`. Either no rule matches (check `number` / `range`
   against the raw values) or the rule is debounced.
4. **`OBS connect failed` repeating.** OBS isn't running, obs-websocket is off,
   or the port/password is wrong. Backoff 1s→30s; it connects once OBS is up.
5. **`cannot split_record_file: obs-websocket has no SplitRecordFile`.** OBS
   older than 30.2. Update it, or use `stop_record` + `start_record`.
6. **Waveform does nothing on a `midi_out` rule.** Check the CC numbers match
   between config and the learned Control Surface, and that IAC Driver Bus 1 is
   online and selected as the surface's input.
7. **Agent keeps restarting.** Check `~/Library/Logs/midi-pedald/launchd.err.log`
   — usually a bad config. Fix it and `launchctl kickstart -k
   gui/$(id -u)/pro.kyxap.midi-pedald`.

## Build from source

```sh
pip install -r requirements.txt -r packaging/requirements-build.txt
packaging/build-pkg.sh
```

Produces `dist/midi-pedald-<version>.pkg`. Requires arm64 macOS.

## Tests

```sh
python -m pytest                    # needs pyyaml, mido, pytest
python3 tests/test_mapping.py       # pure-logic files run with no deps
```

`tests/` covers mapping, per-rule debounce under multi-fire, config validation,
the OBS and MIDI sinks, the BPM latch, and daemon glue — all against fakes, no
hardware or OBS.

## Not in scope

Signing / notarisation, tempo delivery to Waveform, automating the Control
Surface mapping, Intel builds, file upload or post-processing, Windows/Linux.
