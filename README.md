# pedald

A macOS daemon that listens on a MIDI input and drives OBS Studio recording over
[obs-websocket](https://github.com/obsproject/obs-websocket). Built for a Boss
RC-5 looper wired into a Focusrite Scarlett MIDI IN: the pedal starts and stops
recording, each take a separate file.

It reacts to MIDI **Start** (`0xFA`), **Stop** (`0xFC`), **Continue** (`0xFB`),
**Program Change** and **Control Change**. MIDI Clock (`0xF8`) is dropped before
any logic runs.

## Requirements

- Python 3.11+
- OBS Studio 28+ with obs-websocket enabled
  (*Tools → WebSocket Server Settings → Enable*)
- OBS Studio **30.2+** only if you use the `split_record_file` action
  (the `SplitRecordFile` request landed in obs-websocket 5.5.0 — see
  [Split file support](#split-file-support))

## Install

```sh
git clone <this repo> midi-pedald
cd midi-pedald
./install.sh
```

`install.sh` creates `.venv/`, installs `mido`, `python-rtmidi`, `obsws-python`
and `PyYAML` into it, copies `config.example.yaml` to `config.yaml` if you don't
have one, renders the launchd plist with the real paths, and loads the agent.

Then edit `config.yaml` (at minimum: `midi.port_substring` and `obs.password`)
and reload:

```sh
launchctl unload ~/Library/LaunchAgents/pro.kyxap.pedald.plist
launchctl load  ~/Library/LaunchAgents/pro.kyxap.pedald.plist
```

To run in the foreground instead (for testing):

```sh
.venv/bin/python -m pedald --config config.yaml
```

## Finding your MIDI port name

```sh
.venv/bin/python -m pedald --monitor
```

This prints every available MIDI input, then every incoming message on the first
one (or on `--port <substring>` if given): raw bytes, parsed type, channel,
values, timestamp. MIDI Clock and Active Sensing are hidden; add `--show-clock`
to see them.

```
Available MIDI inputs:
  - Scarlett 18i16 USB
  - IAC Driver Bus 1

Monitoring: Scarlett 18i16 USB   (Ctrl-C to stop)

14:22:07.031  FA           start           -
14:22:19.884  C0 04        program_change  ch1   program=4
14:22:31.512  FC           stop            -
```

Put a stable, unique substring of that name (`"Scarlett"`) into
`midi.port_substring`. The daemon matches case-insensitively and re-scans every
2 seconds, so the exact name may change between reboots.

## Config format

YAML. See `config.example.yaml` for a working file.

```yaml
midi:
  port_substring: "Scarlett"      # required

obs:
  host: localhost
  port: 4455
  password: ""                    # your obs-websocket password

logging:
  level: INFO                     # DEBUG = log every MIDI event and rule decision
  file: "~/Library/Logs/pedald/pedald.log"
  max_bytes: 1048576              # rotate at this size
  backup_count: 3

rules:
  - event: start
    action: start_record
    debounce_ms: 500
```

### Rules

Evaluated top to bottom; the **first** matching rule wins. Each rule:

| key           | meaning |
|---------------|---------|
| `event`       | `start` \| `stop` \| `continue` \| `program_change` \| `control_change` |
| `action`      | see table below |
| `debounce_ms` | ignore repeats of this rule within this window (default `300`) |
| `number`      | exact Program Change program, or exact CC controller number |
| `range`       | `[lo, hi]` inclusive Program Change range |
| `value_range` | `[lo, hi]` inclusive CC value range |

`number` / `range` / `value_range` are **raw wire values, 0–127**. The RC-5
shows memory numbers starting at 1, so its "memory 1" is likely Program Change
`0` on the wire — confirm with `--monitor`.

Actions:

| action                | effect |
|-----------------------|--------|
| `start_record`        | start recording (skipped if already recording) |
| `stop_record`         | stop recording (skipped if not recording) |
| `toggle_record`       | toggle recording |
| `split_record_file`   | close the current file, start a new one (OBS 30.2+) |
| `save_replay_buffer`  | save the replay buffer |
| `start_replay_buffer` | start the replay buffer |
| `stop_replay_buffer`  | stop the replay buffer |
| `noop`                | match and do nothing (useful to shadow a later rule) |

`start_record` / `stop_record` check `GetRecordStatus` first, so a doubled
pedal press or a repeated MIDI message never raises.

## Autostart

Managed by a launchd user agent (`pro.kyxap.pedald`, `RunAtLoad` + `KeepAlive`).

- **Install / update:** `./install.sh`
- **Remove:** `./uninstall.sh` (leaves `.venv/`, `config.yaml` and logs in place)
- **Restart:** `launchctl kickstart -k gui/$(id -u)/pro.kyxap.pedald`
- **Is it running:** `launchctl list | grep pro.kyxap.pedald`

The plist is generated from `packaging/pedald.plist`;
`install.sh` substitutes the venv Python path, project dir, config path and log
dir. Don't hand-edit the installed plist — edit the template and re-run
`install.sh`.

## Logs

- stdout (visible in the foreground; captured to
  `~/Library/Logs/pedald/launchd.out.log` under launchd)
- `~/Library/Logs/pedald/pedald.log`, rotated by size

`INFO` covers recording state changes and connection events. `DEBUG` adds every
accepted MIDI event and the rule decision (which rule fired, or why none did).

## Nothing is coming through?

1. **`--monitor` shows no inputs.** The Scarlett isn't presenting a MIDI port.
   Check the USB cable and that the interface shows up in *Audio MIDI Setup →
   MIDI Studio*.
2. **`--monitor` lists the port but no messages on pedal press.** The MIDI chain
   isn't reaching the Scarlett IN. Check each pedal's MIDI THRU/OUT. On the RC-5:
   `SETUP → MIDI`, `CLOCK OUT = ON`, and `PC OUT = ON` if you want Program
   Change on memory switches.
3. **Messages show in `--monitor` but the daemon does nothing.** Set
   `logging.level: DEBUG` and watch the log. Either no rule matches the event
   (check `number` / `range` against the raw values `--monitor` prints) or the
   rule is being debounced (raise or lower `debounce_ms`).
4. **`OBS connect failed` on repeat.** OBS isn't running, obs-websocket is
   disabled, or the port/password is wrong. The daemon retries with backoff
   (1s → 30s); it will connect once OBS is up.
5. **`cannot split_record_file: obs-websocket has no SplitRecordFile request`.**
   Your OBS is older than 30.2. Update OBS, or map that pedal to
   `stop_record` + `start_record` on separate presses instead.
6. **Daemon keeps restarting under launchd.** Check
   `~/Library/Logs/pedald/launchd.err.log` — usually a bad config path or a
   venv that didn't build. Re-run `./install.sh`.

## Split file support

`split_record_file` calls the obs-websocket `SplitRecordFile` request, **added
in obs-websocket 5.5.0**, which ships with **OBS Studio 30.2**. On connect the
daemon reads `GetVersion.availableRequests`; if `SplitRecordFile` is absent it
logs a warning at startup and every `split_record_file` action logs a clear
error instead of crashing.

For the RC-5 "each take a separate file" workflow you don't need it: mapping
`start → start_record` and `stop → stop_record` already produces one file per
take.

## Tests

```sh
python -m pytest            # if pytest is installed
python tests/test_mapping.py   # or run any test file directly, no deps needed
```

`tests/` covers event→action mapping, per-rule debounce, and the
repeat-command / capability guards, using fake MIDI messages and a fake OBS
client (`tests/fakes.py`). No real OBS or MIDI hardware is touched.

## Not in scope

File upload, renaming recordings, any post-processing — separate stage, not
handled here.
