"""OBS-websocket controller: lazy connect with exponential backoff, state-guarded
record commands, and a capability gate for requests missing on older OBS builds.

`obsws_python` is imported lazily inside the default factory so this module (and
its tests) load without the dependency installed.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("pedald")

_BACKOFF_START = 1.0
_BACKOFF_MAX = 30.0

# action -> obs-websocket request name that must appear in GetVersion.availableRequests.
# SplitRecordFile landed in obs-websocket 5.5.0 (OBS Studio 30.2); everything else
# in the mapping has existed since 5.0.0.
_GATED = {"split_record_file": "SplitRecordFile"}


def _default_factory(cfg):
    import obsws_python

    return obsws_python.ReqClient(
        host=cfg.host, port=cfg.port, password=cfg.password, timeout=3
    )


def _is_request_error(exc: BaseException) -> bool:
    """True for obsws_python.error.OBSSDKRequestError without importing it."""
    return type(exc).__name__ == "OBSSDKRequestError"


class ObsController:
    def __init__(self, obs_cfg, client_factory=_default_factory, now=time.monotonic):
        self.cfg = obs_cfg
        self._factory = client_factory
        self._now = now
        self._client = None
        self._available: set[str] = set()
        self._warned_missing: set[str] = set()
        self._backoff = _BACKOFF_START
        self._next_attempt = 0.0

    @property
    def connected(self) -> bool:
        return self._client is not None

    def ensure_connected(self, now: float | None = None) -> bool:
        if self._client is not None:
            return True
        now = self._now() if now is None else now
        if now < self._next_attempt:
            return False
        try:
            self._client = self._factory(self.cfg)
            self._available = self._probe_capabilities()
            self._backoff = _BACKOFF_START
            log.info("OBS connected")
            return True
        except Exception as e:
            self._client = None
            self._next_attempt = now + self._backoff
            log.info("OBS connect failed (%s); retrying in %.0fs", e, self._backoff)
            self._backoff = min(self._backoff * 2, _BACKOFF_MAX)
            return False

    def _probe_capabilities(self) -> set[str]:
        try:
            v = self._client.get_version()
            reqs = set(getattr(v, "available_requests", []) or [])
            log.info(
                "OBS %s / obs-websocket %s",
                getattr(v, "obs_version", "?"),
                getattr(v, "obs_web_socket_version", "?"),
            )
            if "SplitRecordFile" not in reqs:
                log.warning(
                    "this OBS lacks SplitRecordFile (needs OBS Studio 30.2+); "
                    "the split_record_file action will report an error"
                )
            return reqs
        except Exception:
            return set()

    def _drop(self, why: str) -> None:
        if self._client is not None:
            log.info("OBS connection lost: %s", why)
        self._client = None
        self._available = set()
        self._next_attempt = self._now() + self._backoff
        self._backoff = min(self._backoff * 2, _BACKOFF_MAX)

    def dispatch(self, action: str) -> None:
        if action == "noop":
            return
        if not self.ensure_connected():
            log.info("skipping %s: OBS not connected", action)
            return
        cap = _GATED.get(action)
        if cap and cap not in self._available:
            log.error(
                "cannot %s: obs-websocket has no %s request "
                "(SplitRecordFile requires OBS Studio 30.2+)",
                action,
                cap,
            )
            return
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            log.error("unknown action: %s", action)
            return
        try:
            handler()
        except Exception as e:
            if _is_request_error(e):
                log.error("%s failed: %s", action, e)  # bad state, not a dead socket
            else:
                self._drop(f"{action}: {e}")

    def _record_active(self) -> bool:
        return bool(self._client.get_record_status().output_active)

    def _do_start_record(self) -> None:
        if self._record_active():
            log.debug("start_record ignored: already recording")
            return
        self._client.start_record()
        log.info("recording started")

    def _do_stop_record(self) -> None:
        if not self._record_active():
            log.debug("stop_record ignored: not recording")
            return
        self._client.stop_record()
        log.info("recording stopped")

    def _do_toggle_record(self) -> None:
        self._client.toggle_record()
        log.info("recording toggled (active=%s)", self._record_active())

    def _do_split_record_file(self) -> None:
        self._client.split_record_file()
        log.info("record file split")

    def _do_save_replay_buffer(self) -> None:
        self._client.save_replay_buffer()
        log.info("replay buffer saved")

    def _do_start_replay_buffer(self) -> None:
        self._client.start_replay_buffer()
        log.info("replay buffer started")

    def _do_stop_replay_buffer(self) -> None:
        self._client.stop_replay_buffer()
        log.info("replay buffer stopped")
