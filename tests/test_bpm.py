import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from midi_pedald.bpm import BpmMeter  # noqa: E402
from tests.fakes import Clock  # noqa: E402

W = 96


def bar_seconds(bpm):
    return 60.0 * W / (24.0 * bpm)


def meter(**kw):
    clk = Clock()
    return BpmMeter(now=clk, **kw), clk


def prime(m):
    assert m.tick() is None


def window(m, clk, seconds):
    dt = seconds / W
    out = None
    for _ in range(W):
        clk.t += dt
        out = m.tick()
    return out


def close(a, b, eps=1e-4):
    return a is not None and abs(a - b) < eps


def test_first_ever_tick_returns_none_and_does_not_divide_by_zero():
    m, _ = meter()
    assert m.tick() is None
    assert m.latched is None


def test_first_full_window_latches_and_returns_the_value():
    m, clk = meter()
    prime(m)
    assert close(window(m, clk, bar_seconds(120)), 120.0)
    assert close(m.latched, 120.0)


def test_steady_tempo_inside_the_deadband_is_not_relogged():
    m, clk = meter(tolerance=1.5)
    prime(m)
    window(m, clk, bar_seconds(120))
    assert window(m, clk, bar_seconds(120.4)) is None


def test_step_confirmed_on_the_second_consecutive_window():
    m, clk = meter(tolerance=1.5, confirm_windows=2)
    prime(m)
    window(m, clk, bar_seconds(120))
    assert window(m, clk, bar_seconds(140)) is None
    assert close(window(m, clk, bar_seconds(140)), 140.0)
    assert close(m.latched, 140.0)


def test_single_out_of_band_window_then_return_does_not_move_the_latch():
    m, clk = meter(tolerance=1.5, confirm_windows=2)
    prime(m)
    window(m, clk, bar_seconds(120))
    assert window(m, clk, bar_seconds(140)) is None
    assert window(m, clk, bar_seconds(120)) is None
    assert close(m.latched, 120.0)


def test_two_different_out_of_band_windows_do_not_confirm_each_other():
    m, clk = meter(tolerance=1.5, confirm_windows=2)
    prime(m)
    window(m, clk, bar_seconds(120))
    assert window(m, clk, bar_seconds(140)) is None
    assert window(m, clk, bar_seconds(200)) is None
    assert close(m.latched, 120.0)


def test_implausible_windows_are_discarded_and_leave_the_latch_untouched():
    m, clk = meter()
    prime(m)
    window(m, clk, bar_seconds(120))
    assert window(m, clk, bar_seconds(15)) is None
    assert window(m, clk, bar_seconds(900)) is None
    assert close(m.latched, 120.0)


def test_one_dropped_tick_per_window_stays_inside_the_deadband():
    m, clk = meter(tolerance=1.5, confirm_windows=2)
    prime(m)
    window(m, clk, bar_seconds(120))
    # 96 counted ticks but 97 intervals of elapsed time (one THRU pedal ate a tick)
    assert window(m, clk, bar_seconds(120) * 97 / 96) is None
    assert close(m.latched, 120.0)


def test_start_resets_the_partial_window():
    m, clk = meter()
    prime(m)
    for _ in range(50):
        clk.t += 0.01
        assert m.tick() is None
    m.reset()
    for _ in range(50):
        clk.t += 0.01
        assert m.tick() is None  # < W counted since the reset


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print(f"ok  {name}")
    print(f"\n{n} passed")
