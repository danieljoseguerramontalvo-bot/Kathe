"""No look-ahead, end to end: changing the future must not change the past.

For every strategy, all M1 bars at or after a cut time are perturbed (prices and spreads).
Every trade that closed before the cut, and every skipped signal before the cut, must be
identical between the two runs. Also: signals are executed at the first M1 open at or after
the close of the signal bar.
"""
import numpy as np
import pandas as pd
import pytest

from conftest import perturb_after
from kq.data import tf_ns
from kq.engine import BacktestConfig, run_backtest
from kq.strategies import make_strategy

CASES = [
    ("REF_T0", {"adx_min": 0.0, "max_spread_points": None}),
    ("REF_T0", {}),
    ("REF_RSI2", {"timeframe": "M15", "adx_filter": True, "htf_filter": True, "trail_atr": 2.0}),
    ("REF_RSI2", {"timeframe": "H4", "warmup_bars": 250}),
    ("TREND_DONCHIAN", {"timeframe": "H4", "n": 20}),
    ("TREND_DONCHIAN", {"timeframe": "D1", "n": 20}),
    ("SESSION_BREAKOUT", {}),
    ("SESSION_BREAKOUT", {"c_max": None, "tp_mult": None}),
    ("SESSION_DRIFT", {}),
    ("SESSION_DRIFT", {"h_in": 13, "h_out": 17, "side": -1}),
    ("RANDOM_ENTRY", {"target": "TREND_DONCHIAN", "target_params": {"n": 20}, "p_entry": 0.05, "seed": 3}),
    ("REF_T0", {"adx_min": 0.0, "regime_gate": {"allow_regime": "trend", "er_threshold": 0.2, "pct_window": 60}}),
]
CUT = "2023-10-02 12:00"
COLS = ["side", "decision_time", "entry_time", "entry_price", "lots", "initial_stop", "initial_tp", "exit_time",
        "exit_price", "exit_reason", "net_pnl"]


@pytest.mark.parametrize("name,params", CASES)
def test_future_perturbation_does_not_change_past(synth_md, name, params):
    # D1 decisions execute at the ~01:00 server open, inside the default rollover window:
    # the window is disabled for TREND_DONCHIAN so that the D1 case trades at all
    off = name == "TREND_DONCHIAN"
    config = BacktestConfig(start="2023-03-01", risk_pct=1.0,
                            rollover_from_min=0 if off else 1425, rollover_to_min=0 if off else 75)
    md2 = perturb_after(synth_md, CUT, seed=11)
    a = run_backtest(synth_md, make_strategy(name, params), config)
    b = run_backtest(md2, make_strategy(name, params), config)
    cut = pd.Timestamp(CUT)
    ta = a.trades[a.trades.exit_time < cut][COLS].reset_index(drop=True)
    tb = b.trades[b.trades.exit_time < cut][COLS].reset_index(drop=True)
    assert len(ta) > 0, f"{name}: no trades before the cut, test not meaningful"
    pd.testing.assert_frame_equal(ta, tb)
    sa = a.skipped[a.skipped.time < cut].reset_index(drop=True)
    sb = b.skipped[b.skipped.time < cut].reset_index(drop=True)
    pd.testing.assert_frame_equal(sa, sb)
    # and the future actually changed
    assert not a.trades[COLS].equals(b.trades[COLS])


@pytest.mark.parametrize("tf", ["H4", "D1"])
def test_entries_execute_at_first_m1_open_after_signal_bar_close(synth_md, tf):
    s = make_strategy("TREND_DONCHIAN", {"timeframe": tf, "n": 20})
    # rollover window and spread cap disabled: every entry must fill on the first eligible bar
    res = run_backtest(synth_md, s, BacktestConfig(start="2023-02-01", rollover_from_min=0, rollover_to_min=0,
                                                   max_spread_points=0))
    assert len(res.trades) > 5
    assert (res.trades.entry_delay_min == 0).all()
    bars = synth_md.bars(tf)
    opens = set(bars.index)
    L = pd.Timedelta(tf_ns(tf), "ns")
    t = synth_md.t
    for tr in res.trades.itertuples():
        # the decision time is the close of a TF bar (open + L)
        assert (tr.decision_time - L) in opens
        j = int(np.searchsorted(t, tr.decision_time.value, "left"))
        assert tr.entry_time.value == t[j]                     # first M1 bar >= bar close
        assert j == 0 or t[j - 1] < tr.decision_time.value


def test_ref_t0_uses_only_closed_bars(synth_md):
    """Signal at bar i equals the signal computed on data truncated at the end of bar i."""
    full = make_strategy("REF_T0", {})
    full.prepare(synth_md)
    bars = synth_md.bars("H4")
    for i in (700, 900, 1100, len(bars) - 5):
        end = bars["close_time_ns"].iloc[i]
        md_i = synth_md.slice(end=pd.Timestamp(int(end), unit="ns"))
        part = make_strategy("REF_T0", {})
        part.prepare(md_i)
        assert len(part.bars) == i + 1
        np.testing.assert_array_equal(part.sig[: i + 1], full.sig[: i + 1])
        np.testing.assert_allclose(part.adx[: i + 1], full.adx[: i + 1])
        np.testing.assert_allclose(part.atr[: i + 1], full.atr[: i + 1], equal_nan=True)


def test_delayed_entries_stay_inside_the_deadline(synth_md):
    """With the default rules (rollover window, spread cap 60, 90-min deadline) entries may be
    delayed, but never before the signal is known nor after the deadline."""
    for name, p in [("REF_T0", {}), ("TREND_DONCHIAN", {"timeframe": "D1"}), ("SESSION_BREAKOUT", {})]:
        s = make_strategy(name, p)
        res = run_backtest(synth_md, s, BacktestConfig(start="2023-02-01"))
        L = tf_ns(s.timeframe)
        t = synth_md.t
        for tr in res.trades.itertuples():
            j = int(np.searchsorted(t, tr.decision_time.value, "left"))
            first = t[j]
            bar_open = (first // L) * L
            deadline = min(bar_open + L, bar_open + 90 * 60 * 10**9)
            assert first <= tr.entry_time.value < deadline
            assert tr.entry_spread_pts <= 60
            m = tr.entry_time.hour * 60 + tr.entry_time.minute
            assert not (m >= 1425 or m < 75)
