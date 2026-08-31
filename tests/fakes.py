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
