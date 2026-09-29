"""Fill mechanics of the engine on hand-built M1 bars (Tuesday 2024-01-09, server time)."""
import numpy as np
import pandas as pd
import pytest

from conftest import cfg, flat_rows, make_md
from kq.costs import CostModel
from kq.engine import run_backtest
from kq.strategies import Enter, Exit, SetStop, make_strategy

T0 = "2024-01-09 10:00"


def ts(minute):
    return pd.Timestamp(T0) + pd.Timedelta(minutes=minute)


def scripted(script, tf="M1", **kw):
    return make_strategy("SCRIPTED", {"timeframe": tf, "script": script, **kw})


def set_bar(rows, minute, o=None, h=None, l=None, c=None, spread=None):
    r = rows[minute]
    if o is not None:
        r[1] = o
    if h is not None:
        r[2] = h
    if l is not None:
        r[3] = l
    if c is not None:
        r[4] = c
    if spread is not None:
        r[5] = spread
    r[2] = max(r[1:5])
    r[3] = min(r[1:5])


def test_buy_fills_at_ask_and_exits_at_bid():
    rows = flat_rows(T0, 20, price=2000.0, spread=30)
    for m in range(5, 20):
        set_bar(rows, m, o=2001.0, h=2001.0, l=2001.0, c=2001.0)
    md = make_md(rows)
    # decision at close of the 10:00 bar = 10:01 -> executes at the 10:01 open
    s = scripted({ts(1): [Enter(1, sl_dist=5.0)], ts(5): [Exit()]})
    tr = run_backtest(md, s, cfg()).trades.iloc[0]
    assert tr.entry_time == ts(1)
    assert tr.entry_price == pytest.approx(2000.30)           # bid 2000.00 + 30 points
    assert tr.initial_stop == pytest.approx(1995.30)          # from the quoted ask
    assert tr.exit_time == ts(5)
    assert tr.exit_price == pytest.approx(2001.00)            # long exits at bid
    assert tr.gross_pnl == pytest.approx((2001.00 - 2000.30) * 100)
    assert tr.r_price == pytest.approx(5.0)


def test_sell_fills_at_bid_and_exits_at_ask_with_slippage():
    rows = flat_rows(T0, 20, price=2000.0, spread=30)
    md = make_md(rows)
    s = scripted({ts(1): [Enter(-1, sl_dist=5.0)], ts(5): [Exit()]})
    tr = run_backtest(md, s, cfg(costs=CostModel(slippage_points=3))).trades.iloc[0]
    assert tr.entry_price == pytest.approx(2000.00 - 0.03)    # bid - slippage
    assert tr.initial_stop == pytest.approx(2005.00)          # from the quoted bid
    assert tr.exit_price == pytest.approx(2000.30 + 0.03)     # ask + slippage
    assert tr.gross_pnl == pytest.approx(-(0.33 + 0.03) * 100)


def test_short_stop_triggers_on_ask_not_bid():
    rows = flat_rows(T0, 20, price=2000.0, spread=10)
    # short entry at bid 2000.00, stop 2001.00
    set_bar(rows, 3, h=2000.80, spread=10)   # ask high 2000.90 < stop: no trigger
    set_bar(rows, 6, h=2000.80, spread=30)   # bid high below stop but ask high 2001.10 >= stop
    md = make_md(rows)
    tr = run_backtest(md, scripted({ts(1): [Enter(-1, sl_dist=1.0)]}), cfg()).trades.iloc[0]
    assert tr.exit_time == ts(6)
    assert tr.exit_reason == "sl"
    assert tr.exit_price == pytest.approx(2001.00)
    assert tr.r_net == pytest.approx(-1.0)


def test_long_stop_triggers_on_bid_low_only():
    # entry at ask 2000.50 (spread 50), stop 2000.50 - 1.5 = 1999.00
    rows = flat_rows(T0, 20, price=2000.0, spread=50)
    set_bar(rows, 4, l=1999.01)       # bid low 1 point above the stop: no trigger
    set_bar(rows, 7, l=1999.00)       # bid low touches the stop (ask low 1999.50 would not)
    tr = run_backtest(make_md(rows), scripted({ts(1): [Enter(1, sl_dist=1.5)]}), cfg()).trades.iloc[0]
    assert tr.initial_stop == pytest.approx(1999.00)
    assert tr.exit_time == ts(7) and tr.exit_reason == "sl"
    assert tr.exit_price == pytest.approx(1999.00)


def test_same_bar_sl_and_tp_resolves_to_sl():
    rows = flat_rows(T0, 20, price=2000.0, spread=20)
    set_bar(rows, 4, o=2000.0, h=2001.50, l=1999.00, c=2000.0)
    md = make_md(rows)
    s = scripted({ts(1): [Enter(1, sl_dist=1.0, tp_dist=1.0)]})   # ask 2000.20: SL 1999.20, TP 2001.20
    tr = run_backtest(md, s, cfg()).trades.iloc[0]
    assert tr.exit_time == ts(4)
    assert tr.exit_reason == "sl_same_bar_as_tp"
    assert tr.exit_price == pytest.approx(1999.20)


def test_gap_through_stop_fills_at_open():
    rows = flat_rows(T0, 20, price=2000.0, spread=20)
    for m in range(5, 20):
        set_bar(rows, m, o=1998.0, h=1998.5, l=1997.5, c=1998.0)
    md = make_md(rows)
    tr = run_backtest(md, scripted({ts(1): [Enter(1, sl_dist=1.0)]}), cfg()).trades.iloc[0]
    assert tr.exit_reason == "sl_gap"
    assert tr.exit_price == pytest.approx(1998.0)             # worse than the 1999.20 stop
    assert tr.r_net < -1.0


def test_short_gap_through_stop_fills_at_ask_open():
    rows = flat_rows(T0, 20, price=2000.0, spread=20)
    for m in range(5, 20):
        set_bar(rows, m, o=2003.0, h=2003.0, l=2003.0, c=2003.0)
    md = make_md(rows)
    tr = run_backtest(md, scripted({ts(1): [Enter(-1, sl_dist=1.0)]}), cfg()).trades.iloc[0]
    assert tr.exit_reason == "sl_gap"
    assert tr.exit_price == pytest.approx(2003.20)


def test_gap_through_target_fills_at_target_not_better():
    rows = flat_rows(T0, 20, price=2000.0, spread=20)
    for m in range(5, 20):
        set_bar(rows, m, o=2005.0, h=2005.0, l=2005.0, c=2005.0)
    md = make_md(rows)
    tr = run_backtest(md, scripted({ts(1): [Enter(1, sl_dist=1.0, tp_dist=2.0)]}), cfg()).trades.iloc[0]
    assert tr.exit_reason == "tp_gap"
    assert tr.exit_price == pytest.approx(2002.20)


def test_trailing_stop_never_loosens_and_applies_from_next_bar():
    rows = flat_rows(T0, 30, price=2000.0, spread=20)
    set_bar(rows, 4, l=1999.60)     # before the move: must NOT trigger a stop at 1999.70
    set_bar(rows, 12, l=1999.65)    # after the move: triggers
    md = make_md(rows)
    seen = []

    def script(ctx):
        if ctx.decision_time == pd.Timestamp(ts(1)).value:
            return [Enter(1, sl_dist=2.0)]                     # stop 1998.20
        if ctx.positions:
            p = ctx.positions[0]
            seen.append(p.stop)
            if ctx.decision_time == pd.Timestamp(ts(5)).value:
                return [SetStop(p.id, 1999.70)]                # tighten: accepted from bar 10:05
            if ctx.decision_time == pd.Timestamp(ts(8)).value:
                return [SetStop(p.id, 1998.00)]                # loosen: ignored
        return []

    res = run_backtest(md, scripted(script), cfg())
    tr = res.trades.iloc[0]
    assert all(b >= a for a, b in zip(seen, seen[1:])), seen
    assert tr.stop_updates == 1
    assert tr.final_stop == pytest.approx(1999.70)
    assert tr.exit_time == ts(12) and tr.exit_reason == "trail_sl"
    assert tr.exit_price == pytest.approx(1999.70)


def test_short_trailing_never_loosens():
    rows = flat_rows(T0, 30, price=2000.0, spread=20)
    md = make_md(rows)
    stops = []

    def script(ctx):
        if not ctx.positions and ctx.decision_time == pd.Timestamp(ts(1)).value:
            return [Enter(-1, sl_dist=3.0)]                    # stop 2003.00
        if ctx.positions:
            p = ctx.positions[0]
            stops.append(p.stop)
            k = len(stops)
            return [SetStop(p.id, 2003.0 - 0.1 * k if k % 2 else 2004.0)]   # alternate tighten / loosen
        return []

    run_backtest(md, scripted(script), cfg())
    assert all(b <= a for a, b in zip(stops, stops[1:])), stops
    assert stops[-1] < 2003.0


def test_fill_time_is_first_m1_open_at_or_after_signal_bar_close():
    # M5 strategy; M1 bars missing between 10:05 and 10:07 -> execution at 10:07
    rows = [r for r in flat_rows(T0, 30, price=2000.0, spread=20) if not (5 <= r[0].minute <= 6)]
    md = make_md(rows)
    s = scripted({"2024-01-09 10:05": [Enter(1, sl_dist=1.0)]}, tf="M5")
    res = run_backtest(md, s, cfg())
    tr = res.trades.iloc[0]
    assert tr.decision_time == pd.Timestamp("2024-01-09 10:05")   # close of the 10:00 M5 bar
    assert tr.entry_time == pd.Timestamp("2024-01-09 10:07")
    # every decision context executes at the first M1 bar >= decision time
    for ctx in s.contexts:
        j = int(np.searchsorted(md.t, ctx.decision_time, "left"))
        assert ctx.exec_index == j
        assert md.t[ctx.exec_index] >= ctx.decision_time
        assert ctx.exec_index == 0 or md.t[ctx.exec_index - 1] < ctx.decision_time


def test_rollover_window_skips_entries_without_delay():
    # bars from 00:50 to 01:40 server; window 23:45 -> 01:15
    rows = flat_rows("2024-01-09 00:50", 50, price=2000.0, spread=20)
    md = make_md(rows)
    s = scripted({"2024-01-09 01:00": [Enter(1, sl_dist=1.0)], "2024-01-09 01:15": [Enter(1, sl_dist=1.0)]})
    res = run_backtest(md, s, cfg(rollover_from_min=1425, rollover_to_min=75))
    assert len(res.trades) == 1
    assert res.trades.iloc[0].entry_time == pd.Timestamp("2024-01-09 01:15")
    sk = res.skipped
    assert list(sk.reason) == ["rollover"] and sk.iloc[0].time == pd.Timestamp("2024-01-09 01:00")
    # from == to disables the window
    s2 = scripted({"2024-01-09 01:00": [Enter(1, sl_dist=1.0)]})
    assert len(run_backtest(md, s2, cfg(rollover_from_min=60, rollover_to_min=60)).trades) == 1


def test_max_spread_waits_inside_next_bar():
    rows = flat_rows(T0, 40, price=2000.0, spread=20)
    for m in range(5, 8):
        set_bar(rows, m, spread=120)
    md = make_md(rows)
    s = scripted({"2024-01-09 10:05": [Enter(1, sl_dist=1.0, max_spread_points=80)]}, tf="M5")
    tr = run_backtest(md, s, cfg()).trades.iloc[0]
    assert tr.entry_time == ts(8)
    rows2 = flat_rows(T0, 40, price=2000.0, spread=120)
    s2 = scripted({"2024-01-09 10:05": [Enter(1, sl_dist=1.0, max_spread_points=80)]}, tf="M5")
    res = run_backtest(make_md(rows2), s2, cfg())
    assert len(res.trades) == 0 and res.skipped.iloc[0].reason == "spread_above_max"


def test_equity_marked_to_market_each_m1_close():
    rows = flat_rows(T0, 10, price=2000.0, spread=20)
    set_bar(rows, 3, c=2001.0)
    set_bar(rows, 4, o=2001.0, c=2001.0)
    md = make_md(rows)
    res = run_backtest(md, scripted({ts(1): [Enter(1, sl_dist=5.0)], ts(6): [Exit()]}), cfg())
    eq = res.equity
    assert eq[0] == pytest.approx(10_000)
    assert eq[1] == pytest.approx(10_000 + (2000.0 - 2000.2) * 100)   # held at the 10:01 close
    assert eq[3] == pytest.approx(10_000 + (2001.0 - 2000.2) * 100)
    assert res.in_pos[1:6].all() and not res.in_pos[6:].any()
    assert eq[-1] == pytest.approx(10_000 + res.trades.net_pnl.sum())


def test_d1_entries_fall_in_default_rollover_window_and_are_flagged(synth_md):
    from kq.engine import BacktestConfig
    s = make_strategy("TREND_DONCHIAN", {"timeframe": "D1", "n": 20})
    res = run_backtest(synth_md, s, BacktestConfig(start="2023-03-01"))       # default window 23:45-01:15
    assert len(res.trades) == 0 and (res.skipped.reason == "rollover").sum() > 0
    assert res.stats["warnings"] and "rollover" in res.stats["warnings"][0]
    s = make_strategy("TREND_DONCHIAN", {"timeframe": "D1", "n": 20})
    ok = run_backtest(synth_md, s, BacktestConfig(start="2023-03-01", rollover_from_min=0, rollover_to_min=0))
    assert len(ok.trades) > 0 and not ok.stats["warnings"]
