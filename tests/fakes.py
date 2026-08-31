"""Fake MIDI messages and a fake obsws_python ReqClient. No real hardware/OBS."""
from __future__ import annotations

import types


def midi(type_, raw=(), **fields):
    """A duck-typed stand-in for mido.Message."""
    m = types.SimpleNamespace(type=type_, **fields)
    m.bytes = lambda: list(raw)
    return m


def pc(program, channel=0):
    return midi("program_change", raw=(0xC0 | channel, program), program=program, channel=channel)


def cc(control, value, channel=0):
    return midi(
        "control_change",
        raw=(0xB0 | channel, control, value),
        control=control,
        value=value,
        channel=channel,
    )


def start():
    return midi("start", raw=(0xFA,))


def stop():
    return midi("stop", raw=(0xFC,))


def clock():
    return midi("clock", raw=(0xF8,))


class OBSSDKRequestError(Exception):
    """Name-matched to the real obsws_python error class."""

    def __init__(self, req_name, code=604):
        super().__init__(f"{req_name} failed with code {code}")
        self.req_name = req_name
        self.code = code


class FakeReqClient:
    def __init__(self, active=False, available=("SplitRecordFile",), fail=()):
        self._active = active
        self.available_requests = list(available)
        self.obs_version = "30.2.0"
        self.obs_web_socket_version = "5.5.0"
        self.calls: list[str] = []
        self._fail = set(fail)

    def get_version(self):
        return self

    def get_record_status(self):
        return types.SimpleNamespace(output_active=self._active)

    def _do(self, name):
        self.calls.append(name)
        if name in self._fail:
            raise OBSSDKRequestError(name)

    def start_record(self):
        self._do("start_record")
        self._active = True

    def stop_record(self):
        self._do("stop_record")
        self._active = False

    def toggle_record(self):
        self._do("toggle_record")
        self._active = not self._active

    def split_record_file(self):
        self._do("split_record_file")

    def save_replay_buffer(self):
        self._do("save_replay_buffer")

    def start_replay_buffer(self):
        self._do("start_replay_buffer")

    def stop_replay_buffer(self):
        self._do("stop_replay_buffer")


class Clock:
    """Controllable monotonic clock for tests."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeSink:
    """Records what the daemon dispatches; always 'connected'."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.ensure_calls = 0
        self.connected = True

    def ensure_connected(self, now) -> bool:
        self.ensure_calls += 1
        return True

    def dispatch(self, method, **params) -> None:
        self.calls.append((method, params))


class FakePort:
    def __init__(self, name, callback=None):
        self.name = name
        self.callback = callback
        self.closed = False
        self.sent: list = []

    def send(self, msg):
        self.sent.append(msg)

    def close(self):
        self.closed = True


class FakeMido:
    """Controllable stand-in for the mido module. Port lists are mutable so a
    test can make a port appear or vanish between polls."""

    def __init__(self, inputs=(), outputs=()):
        self.inputs = list(inputs)
        self.outputs = list(outputs)
        self.opened: list[FakePort] = []

    def get_input_names(self):
        return list(self.inputs)

    def get_output_names(self):
        return list(self.outputs)

    def open_input(self, name, callback=None):
        p = FakePort(name, callback)
        self.opened.append(p)
        return p

    def open_output(self, name):
        p = FakePort(name)
        self.opened.append(p)
        return p
