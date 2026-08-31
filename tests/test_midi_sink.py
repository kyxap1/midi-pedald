import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import midi_pedald.midi_sink as midi_sink  # noqa: E402
from midi_pedald.config import MidiOutConfig  # noqa: E402
from midi_pedald.midi_sink import MidiSink  # noqa: E402
from tests.fakes import Clock, FakeMido  # noqa: E402


def sink(outputs=(), clock=None):
    clk = clock or Clock()
    be = FakeMido(outputs=list(outputs))
    s = MidiSink(MidiOutConfig(port_substring="IAC"), backend=be, now=clk)
    return s, be, clk


def test_cc_sequence_sends_two_messages_in_order(monkeypatch):
    sleeps = []
    monkeypatch.setattr(midi_sink.time, "sleep", lambda s: sleeps.append(s))
    s, be, _ = sink(outputs=["IAC Driver Bus 1"])
    s.dispatch("cc_sequence", cc=[[22, 127], [20, 127]], gap_ms=50)
    sent = [(m.type, m.control, m.value, m.channel) for m in be.opened[0].sent]
    assert sent == [("control_change", 22, 127, 0), ("control_change", 20, 127, 0)]
    assert sleeps == [0.05]  # one gap for two CCs, not after the last


def test_dispatch_while_disconnected_sends_nothing_and_does_not_raise():
    s, be, _ = sink(outputs=[])
    s.dispatch("cc_sequence", cc=[[1, 2]], gap_ms=0)
    assert be.opened == []


def test_port_absent_at_startup_then_appears_on_a_later_poll():
    clk = Clock()
    s, be, _ = sink(outputs=[], clock=clk)
    assert s.ensure_connected() is False
    be.outputs.append("IAC Driver Bus 1")
    assert s.ensure_connected() is False  # still inside the 2s poll window
    clk.t = 2.0
    assert s.ensure_connected() is True
    assert s.connected


def test_port_vanishes_while_held_then_reopens():
    clk = Clock()
    s, be, _ = sink(outputs=["IAC Driver Bus 1"], clock=clk)
    assert s.ensure_connected() is True
    be.outputs.clear()
    clk.t = 2.0
    assert s.ensure_connected() is False
    assert not s.connected
    be.outputs.append("IAC Driver Bus 1")
    clk.t = 4.0
    assert s.ensure_connected() is True


def test_disconnected_poll_respects_the_2s_window():
    clk = Clock()
    s, be, _ = sink(outputs=[], clock=clk)
    s.ensure_connected()
    s.ensure_connected()
    assert be.output_scans == 1
    clk.t = 2.0
    s.ensure_connected()
    assert be.output_scans == 2


def test_send_raising_mid_sequence_drops_the_port_and_does_not_propagate(monkeypatch):
    monkeypatch.setattr(midi_sink.time, "sleep", lambda s: None)
    s, be, _ = sink(outputs=["IAC Driver Bus 1"])
    s.ensure_connected()

    def boom(_msg):
        raise OSError("port gone")

    be.opened[0].send = boom
    s.dispatch("cc_sequence", cc=[[22, 127], [20, 127]], gap_ms=1)
    assert not s.connected


def test_empty_cc_list_is_a_noop_not_an_error():
    s, be, _ = sink(outputs=["IAC Driver Bus 1"])
    s.dispatch("cc_sequence", cc=[], gap_ms=50)
    assert be.opened == []


def test_unknown_method_is_logged_not_raised():
    s, _, _ = sink()
    s.dispatch("note", foo=1)
