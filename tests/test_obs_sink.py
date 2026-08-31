import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midi_pedald.obs_sink import ObsController  # noqa: E402
from tests.fakes import Clock, FakeReqClient  # noqa: E402

CFG = types.SimpleNamespace(host="localhost", port=4455, password="")


def controller(client=None, clock=None, **client_kw):
    clk = clock or Clock()
    holder = {"client": client if client is not None else FakeReqClient(**client_kw)}
    oc = ObsController(CFG, client_factory=lambda cfg: holder["client"], now=clk)
    return oc, holder["client"], clk


def test_start_record_when_idle_starts():
    oc, cl, _ = controller(active=False)
    oc.dispatch("start_record")
    assert cl.calls == ["start_record"]


def test_start_record_when_already_recording_is_noop():
    oc, cl, _ = controller(active=True)
    oc.dispatch("start_record")
    assert "start_record" not in cl.calls


def test_stop_record_when_not_recording_is_noop():
    oc, cl, _ = controller(active=False)
    oc.dispatch("stop_record")
    assert "stop_record" not in cl.calls


def test_stop_record_when_recording_stops():
    oc, cl, _ = controller(active=True)
    oc.dispatch("stop_record")
    assert cl.calls == ["stop_record"]


def test_repeated_start_command_never_raises_and_sends_once():
    oc, cl, _ = controller(active=False)
    for _ in range(5):
        oc.dispatch("start_record")
    assert cl.calls == ["start_record"]


def test_split_without_capability_reports_error_no_call():
    oc, cl, _ = controller(available=())  # OBS too old
    oc.dispatch("split_record_file")
    assert cl.calls == []  # no raise, no request


def test_split_with_capability_sends():
    oc, cl, _ = controller(available=("SplitRecordFile",))
    oc.dispatch("split_record_file")
    assert cl.calls == ["split_record_file"]


def test_request_error_does_not_drop_connection():
    oc, cl, _ = controller(fail=("save_replay_buffer",))
    oc.dispatch("save_replay_buffer")
    assert oc.connected is True  # bad state, not a dead socket


def test_dispatch_when_obs_never_connects_is_safe():
    def boom(cfg):
        raise ConnectionRefusedError("no obs")

    oc = ObsController(CFG, client_factory=boom, now=Clock())
    oc.dispatch("start_record")  # must not raise
    assert oc.connected is False


def test_reconnect_backoff_grows_and_does_not_hammer():
    clk = Clock()
    attempts = {"n": 0}

    def flaky(cfg):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionRefusedError("nope")
        return FakeReqClient()

    oc = ObsController(CFG, client_factory=flaky, now=clk)

    assert oc.ensure_connected() is False  # attempt 1; next retry at t=1
    assert oc.ensure_connected() is False  # t=0 still < 1: skipped, not retried
    assert attempts["n"] == 1

    clk.t = 1.0
    assert oc.ensure_connected() is False  # attempt 2; backoff now 2, next retry t=3
    assert attempts["n"] == 2

    clk.t = 2.0
    assert oc.ensure_connected() is False  # 2 < 3: skipped
    assert attempts["n"] == 2

    clk.t = 3.0
    assert oc.ensure_connected() is True  # attempt 3 succeeds
    assert oc.connected is True


def test_noop_action_does_nothing():
    oc, cl, _ = controller()
    oc.dispatch("noop")
    assert cl.calls == []


def test_dispatch_ignores_unexpected_kwargs():
    oc, cl, _ = controller(active=False)
    oc.dispatch("start_record", cc=[[22, 127]], gap_ms=50)  # params meant for another sink
    assert cl.calls == ["start_record"]


def _with_obs_ws_file(payload):
    """Point obs_sink at a temp obs-websocket config.json; returns a restore fn."""
    import json
    import tempfile

    from midi_pedald import obs_sink

    d = tempfile.mkdtemp()
    p = Path(d) / "config.json"
    p.write_text(json.dumps(payload))
    old = obs_sink._OBS_WS_CONFIG
    obs_sink._OBS_WS_CONFIG = p

    def restore():
        obs_sink._OBS_WS_CONFIG = old
        p.unlink()
        Path(d).rmdir()

    return restore


def test_conn_autodetected_from_obs_websocket_config():
    from midi_pedald import obs_sink
    from midi_pedald.config import ObsConfig

    restore = _with_obs_ws_file(
        {"server_port": 4499, "server_password": "sekret", "auth_required": True}
    )
    try:
        assert obs_sink._resolve_conn(ObsConfig()) == ("localhost", 4499, "sekret")
        # an explicit daemon-config value wins over the detected one
        assert obs_sink._resolve_conn(ObsConfig(port=9999, password="mine")) == (
            "localhost",
            9999,
            "mine",
        )
    finally:
        restore()


def test_conn_ignores_password_when_obs_auth_disabled():
    from midi_pedald import obs_sink
    from midi_pedald.config import ObsConfig

    restore = _with_obs_ws_file(
        {"server_port": 4499, "server_password": "sekret", "auth_required": False}
    )
    try:
        assert obs_sink._resolve_conn(ObsConfig()) == ("localhost", 4499, "")
    finally:
        restore()


def test_conn_falls_back_to_defaults_without_obs_config():
    from midi_pedald import obs_sink
    from midi_pedald.config import ObsConfig

    old = obs_sink._OBS_WS_CONFIG
    obs_sink._OBS_WS_CONFIG = Path("/nonexistent/obs-websocket/config.json")
    try:
        assert obs_sink._resolve_conn(ObsConfig()) == ("localhost", 4455, "")
    finally:
        obs_sink._OBS_WS_CONFIG = old


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
