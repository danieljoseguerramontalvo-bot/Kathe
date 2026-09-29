"""Strategy-specific rules."""
import numpy as np
import pandas as pd
import pytest

from kq.data import last_closed_index
from kq.engine import BacktestConfig, run_backtest
from kq.indicators import atr_mt5
from kq.strategies import BarContext, Exit, PositionView, SetStop, Skip, make_strategy
from kq.timeutil import NS_PER_DAY, NS_PER_MIN, server_to_utc

NO_ROLL = dict(rollover_from_min=0, rollover_to_min=0)


def _ctx(md, strat, i, positions=()):
    dt = int(strat.decision_times()[i])
    e = int(np.searchsorted(md.t, dt))
    return BarContext(i, dt, int(server_to_utc(np.array([dt]))[0]), e, int(md.t[min(e, len(md.t) - 1)]),
                      list(positions), 10_000.0, md)


def _long_pos(md, j=0, stop=1.0):
    return PositionView(1, 1, 0.1, j, int(md.t[j]), int(md.t_utc[j]), 2000.0, stop, None, stop, 0)


# ----------------------------------------------------------------------------- REF_T0
def test_ref_t0_opposite_signal_closes_even_if_adx_blocks_new_entry(synth_md):
    s = make_strategy("REF_T0", {})
    s.prepare(synth_md)
    i = 1000
    s.sig[i] = -1
    s.adx[i] = 5.0
    acts = s.on_bar(_ctx(synth_md, s, i, [_long_pos(synth_md)]))
    assert any(isinstance(a, Exit) and a.reason == "opposite_signal" for a in acts)
    assert any(isinstance(a, Skip) and a.reason.startswith("adx_below_min") for a in acts)
    s.adx[i] = 35.0
    acts = s.on_bar(_ctx(synth_md, s, i, [_long_pos(synth_md)]))
    kinds = [type(a).__name__ for a in acts]
    assert kinds == ["Exit", "Enter"] and acts[1].side == -1


def test_ref_t0_ignores_signals_during_warmup(synth_md):
    s = make_strategy("REF_T0", {})
    s.prepare(synth_md)
    # EA: warming up while Bars() (closed bars + the forming one = i + 2) < 3 * 200
    assert not s.ready(597) and s.ready(598)
    s.sig[500] = 1
    assert s.on_bar(_ctx(synth_md, s, 500)) == []


def test_ref_t0_stops_are_atr_multiples_of_the_signal_bar(synth_md):
    s = make_strategy("REF_T0", {"max_spread_points": None})
    res = run_backtest(synth_md, s, BacktestConfig(start="2023-03-01"))
    assert len(res.trades) >= 5
    for tr in res.trades.itertuples():
        a = s.atr[tr.decision_index]
        assert tr.initial_stop == pytest.approx(round(tr.entry_ref_price - tr.side * 1.5 * a, 2), abs=1e-9)
        assert tr.initial_tp == pytest.approx(round(tr.entry_ref_price + tr.side * 3.0 * a, 2), abs=1e-9)


# ----------------------------------------------------------------------------- TREND_DONCHIAN
def test_donchian_chandelier_matches_ea_definition(synth_md):
    s = make_strategy("TREND_DONCHIAN", {"timeframe": "H4", "n": 20, "k_trail": 3.0})
    res = run_backtest(synth_md, s, BacktestConfig(start="2023-02-01", **NO_ROLL))
    assert res.stats["n_stop_moves"] > 0
    c, spr = synth_md.c, synth_md.spread * synth_md.spec.point
    bars = synth_md.bars("H4")
    close_t = bars["close_time_ns"].to_numpy()
    exec_idx = np.searchsorted(synth_md.t, close_t)
    h, l = bars["high"].to_numpy(), bars["low"].to_numpy()
    checked = 0
    for tr in res.trades.itertuples():
        j_entry = int(np.searchsorted(synth_md.t, tr.entry_time.value))
        j_exit = int(np.searchsorted(synth_md.t, tr.exit_time.value))
        e = s.bar_index_of_m1(j_entry)
        stop = tr.initial_stop
        # decisions whose close is after entry and whose execution bar is not after the exit bar
        for i in range(e, len(bars)):
            if close_t[i] <= tr.entry_time.value or exec_idx[i] > j_exit:
                if exec_idx[i] > j_exit:
                    break
                continue
            if tr.exit_reason not in ("sl", "trail_sl", "sl_gap", "trail_sl_same_bar_as_tp") and exec_idx[i] == j_exit:
                break      # exit at the open of that bar happens before the new stop applies
            jc = exec_idx[i] - 1                 # last M1 bar at the decision (bar close)
            if tr.side > 0:
                lvl = round(h[e:i + 1].max() - 3.0 * s.atr[i], 2)
                if lvl < c[jc]:                  # a valid SL must be below the bid (MT5)
                    stop = max(stop, lvl)
            else:
                lvl = round(l[e:i + 1].min() + 3.0 * s.atr[i], 2)
                if lvl > round(c[jc] + spr[jc], 2):
                    stop = min(stop, lvl)
        assert tr.final_stop == pytest.approx(stop, abs=1e-9), tr
        checked += 1
    assert checked >= 10


def test_donchian_breakout_uses_previous_channel(synth_md):
    s = make_strategy("TREND_DONCHIAN", {"n": 20})
    s.prepare(synth_md)
    i = np.flatnonzero(s.sig == 1)[5]
    assert s.b_close[i] > s.b_high[i - 20:i].max()
    k = np.flatnonzero(s.sig == -1)[5]
    assert s.b_close[k] < s.b_low[k - 20:k].min()


# ----------------------------------------------------------------------------- SESSION_BREAKOUT
def test_session_breakout_rules(synth_md):
    s = make_strategy("SESSION_BREAKOUT", {"c_max": None})
    res = run_backtest(synth_md, s, BacktestConfig(start="2023-02-01"))
    tr = res.trades
    assert len(tr) > 50
    assert tr.entry_time_utc.dt.date.is_unique                       # at most one trade per day
    tu = synth_md.t_utc
    for t in tr.itertuples():
        dec_utc = pd.Timestamp(int(server_to_utc(np.array([t.decision_time.value]))[0]))
        assert pd.Timedelta("07:05:00") <= dec_utc - dec_utc.normalize() <= pd.Timedelta("12:00:00")
        d0 = t.entry_time_utc.normalize().value
        a, b = np.searchsorted(tu, d0), np.searchsorted(tu, d0 + 7 * 60 * NS_PER_MIN)
        rh, rl = synth_md.h[a:b].max(), synth_md.l[a:b].min()
        assert t.initial_stop == pytest.approx(rl if t.side > 0 else rh)
        assert t.initial_tp == pytest.approx(round(t.entry_ref_price + t.side * 2.0 * (rh - rl), 2))
        flat = t.entry_time_utc.normalize() + pd.Timedelta(hours=20)
        if t.exit_reason == "session_flat":
            assert flat <= t.exit_time_utc <= flat + pd.Timedelta(minutes=5)
        else:
            assert t.exit_time_utc <= flat


def test_session_breakout_compression_filter_skips_days(synth_md):
    loose = run_backtest(synth_md, make_strategy("SESSION_BREAKOUT", {"c_max": None}), BacktestConfig(start="2023-02-01"))
    tight = run_backtest(synth_md, make_strategy("SESSION_BREAKOUT", {"c_max": 0.4}), BacktestConfig(start="2023-02-01"))
    assert len(tight.trades) < len(loose.trades)
    assert (tight.skipped.reason == "compression_filter").sum() > 0


def test_random_anchor_windows_same_length_before_entry_and_seeded(synth_md):
    a = make_strategy("SESSION_BREAKOUT", {"anchor_mode": "random", "anchor_seed": 1})
    b = make_strategy("SESSION_BREAKOUT", {"anchor_mode": "random", "anchor_seed": 1})
    c = make_strategy("SESSION_BREAKOUT", {"anchor_mode": "random", "anchor_seed": 2})
    f = make_strategy("SESSION_BREAKOUT", {"anchor_mode": "fixed"})
    for s in (a, b, c, f):
        s.prepare(synth_md)
    np.testing.assert_array_equal(a.day_ws, b.day_ws)
    assert (a.day_ws != c.day_ws).mean() > 0.5
    L = 7 * 60 * NS_PER_MIN
    E = a.days * NS_PER_DAY + 7 * 60 * NS_PER_MIN
    assert np.all(a.day_ws + L <= E) and np.all(a.day_ws >= E - NS_PER_DAY)
    np.testing.assert_array_equal(f.day_ws, f.days * NS_PER_DAY)       # real window starts 00:00 UTC


# ----------------------------------------------------------------------------- SESSION_DRIFT
def test_session_drift_default_long_asia_session(synth_md):
    s = make_strategy("SESSION_DRIFT", {})
    assert (s.params["h_in"], s.params["h_out"], s.params["side"], s.params["sl_atr"]) == (0, 8, 1, 3.0)
    res = run_backtest(synth_md, s, BacktestConfig(start="2023-02-01"))
    tr = res.trades
    assert len(tr) > 100 and (tr.side == 1).all()
    assert (tr.entry_time_utc.dt.hour == 0).all() and (tr.entry_time_utc.dt.minute < 5).all()
    te = tr[tr.exit_reason == "time_exit"]
    assert len(te) > 0 and (te.exit_time_utc.dt.hour == 8).all()
    h1 = synth_md.bars("H1")
    for t in tr.head(20).itertuples():
        k = int(last_closed_index(h1["close_time_ns"].to_numpy(), t.decision_time.value))
        assert t.initial_stop == pytest.approx(round(t.entry_ref_price - 3.0 * s.atr[k], 2))


# ----------------------------------------------------------------------------- RANDOM_ENTRY / gate
def test_random_entry_is_seeded_and_uses_target_stops(synth_md):
    p = {"target": "REF_T0", "target_params": {"max_spread_points": None}, "p_entry": 0.05}
    cfg = BacktestConfig(start="2023-03-01")
    a = run_backtest(synth_md, make_strategy("RANDOM_ENTRY", {**p, "seed": 1}), cfg).trades
    b = run_backtest(synth_md, make_strategy("RANDOM_ENTRY", {**p, "seed": 1}), cfg).trades
    c = run_backtest(synth_md, make_strategy("RANDOM_ENTRY", {**p, "seed": 2}), cfg).trades
    pd.testing.assert_frame_equal(a, b)
    assert not a.entry_time.equals(c.entry_time)
    assert set(a.side) == {1, -1}
    tgt = make_strategy("REF_T0", {})
    tgt.prepare(synth_md)
    for t in a.itertuples():
        atr = tgt.atr[t.decision_index]
        assert t.initial_stop == pytest.approx(round(t.entry_ref_price - t.side * 1.5 * atr, 2), abs=1e-9)


def test_regime_gate_only_blocks_entries(synth_md):
    cfg = BacktestConfig(start="2023-03-01")
    free = run_backtest(synth_md, make_strategy("TREND_DONCHIAN", {}), cfg)
    blocked = run_backtest(synth_md, make_strategy("TREND_DONCHIAN", {"regime_gate": {
        "allow_regime": "trend", "er_threshold": 1.01, "pct_window": 60}}), cfg)
    assert len(free.trades) > 0 and len(blocked.trades) == 0
    assert set(blocked.skipped.reason) <= {"regime_not_trend", "regime_warmup", "rollover"}
    assert blocked.strategy["params"]["regime_gate"]["er_threshold"] == 1.01


def test_rsi2_exits_and_trailing(synth_md):
    s = make_strategy("REF_RSI2", {"timeframe": "M15", "trail_atr": 2.0})
    res = run_backtest(synth_md, s, BacktestConfig(start="2023-03-01"))
    tr = res.trades
    assert "rsi_exit" in set(tr.exit_reason)
    assert (tr.stop_updates > 0).any()
    lg, sh = tr[tr.side > 0], tr[tr.side < 0]
    assert (lg.final_stop >= lg.initial_stop).all() and (sh.final_stop <= sh.initial_stop).all()
    for t in tr[tr.exit_reason == "rsi_exit"].head(20).itertuples():
        # the exit decision came from a closed bar whose RSI crossed the exit level
        close_ns = t.exit_time.value
        i = int(np.searchsorted(s.bars["close_time_ns"].to_numpy(), close_ns, "right") - 1)
        while s.bars["close_time_ns"].to_numpy()[i] > close_ns:
            i -= 1
        assert (s.rsi[i] > 70) if t.side > 0 else (s.rsi[i] < 30)


def test_unknown_parameter_rejected():
    with pytest.raises(ValueError):
        make_strategy("REF_T0", {"adx_minimum": 20})
    with pytest.raises(ValueError):
        make_strategy("NOPE", {})
