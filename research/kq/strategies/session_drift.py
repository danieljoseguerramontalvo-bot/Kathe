"""SESSION_DRIFT — hypothesis: time-of-day seasonality.

Enter at the open of UTC hour ``h_in`` (first M1 bar at or after hh:00 UTC, within
``max_exec_delay_min``), exit at the open of UTC hour ``h_out``, fixed direction, protective
SL = ``sl_atr`` * ATR14(H1) of the last CLOSED H1 bar. Server time is a whole number of
hours from UTC, so UTC hour boundaries are server hour boundaries.

Confirmatory default (pre-registered): LONG from 00:00 to 08:00 UTC (Asia session).

``scan_session_windows`` is an EXPLORATORY helper: on a given date range only, it scans every
(h_in, duration 1..12 h, direction) window, reports net mean / t-stat after costs and returns
the best one plus the number of windows tried (for multiple-testing corrections). A window
found by the scan must be confirmed on data not used by the scan.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from ..costs import CostModel
from ..data import MarketData, last_closed_index
from ..indicators import atr_mt5
from ..timeutil import NS_PER_DAY, NS_PER_HOUR, NS_PER_MIN, server_to_utc, to_ns, weekday_of_ns
from .base import Exit, Strategy


class SessionDrift(Strategy):
    name = "SESSION_DRIFT"
    default_params = {
        "timeframe": "H1",          # used for the ATR of the protective stop
        "h_in": 0,                  # UTC hour of entry
        "h_out": 8,                 # UTC hour of exit
        "side": 1,                  # +1 long, -1 short
        "sl_atr": 3.0,
        "atr_period": 14,
        "tp_atr": None,
        "weekdays": None,           # UTC weekdays allowed for entry (Mon=0); None = all
        "max_exec_delay_min": 59,   # skip if the first M1 bar is later than this after hh:00
        "skip_weekend_cross": True, # do not enter if the planned exit falls on the weekend
        "close_on_opposite": False,
        "max_spread_points": None,
    }

    def prepare(self, md):
        super().prepare(md)
        p = self.params
        self.dur_h = (int(p["h_out"]) - int(p["h_in"])) % 24
        if self.dur_h == 0:
            raise ValueError("h_out must differ from h_in")
        if int(p["side"]) not in (1, -1):
            raise ValueError("side must be +1 or -1")
        self.atr = atr_mt5(self.b_high, self.b_low, self.b_close, p["atr_period"])
        self.h1_close = self.bars["close_time_ns"].to_numpy("int64")
        first = (int(md.t[0]) // NS_PER_HOUR) * NS_PER_HOUR
        self.grid = np.arange(first, int(md.t[-1]) + NS_PER_HOUR, NS_PER_HOUR, dtype="int64")
        self.grid_utc = server_to_utc(self.grid)
        self.grid_hour = (self.grid_utc % NS_PER_DAY) // NS_PER_HOUR
        self.grid_wd = weekday_of_ns(self.grid_utc)
        # a grid hour is 'live' when the market has an M1 bar within the delay tolerance
        j = np.minimum(np.searchsorted(md.t, self.grid, "left"), len(md.t) - 1)
        self.grid_live = (md.t[j] >= self.grid) & (md.t[j] - self.grid <= int(p["max_exec_delay_min"]) * NS_PER_MIN)

    def decision_times(self):
        return self.grid

    def signal(self, i):
        p = self.params
        if self.grid_hour[i] != int(p["h_in"]) or not self.grid_live[i]:
            return 0      # not the entry hour, or market closed (weekend/holiday): silent
        if p["weekdays"] is not None and int(self.grid_wd[i]) not in set(p["weekdays"]):
            return 0
        return int(p["side"])

    def _atr_at(self, t_ns):
        k = int(last_closed_index(self.h1_close, t_ns))
        return self.atr[k] if k >= 0 else np.nan

    def entry_block_reason(self, ctx, side):
        p = self.params
        if ctx.exec_time - ctx.decision_time > int(p["max_exec_delay_min"]) * NS_PER_MIN:
            return "market_closed_at_entry_hour"
        if p["skip_weekend_cross"] and weekday_of_ns(ctx.decision_time + self.dur_h * NS_PER_HOUR) >= 5:
            return "would_cross_weekend"
        a = self._atr_at(ctx.decision_time)
        if not np.isfinite(a) or a <= 0:
            return "atr_warmup"
        return None

    def entry_window_ok(self, ctx):
        return self.grid_hour[ctx.i] == int(self.params["h_in"])

    def stops(self, ctx, side):
        a = self._atr_at(ctx.decision_time)
        if not np.isfinite(a) or a <= 0:
            return None
        tp = self.params["tp_atr"]
        return {"sl_dist": float(self.params["sl_atr"]) * a, "tp_dist": float(tp) * a if tp else None}

    def manage(self, ctx, pos):
        due = self.grid_utc[pos.decision_index] + self.dur_h * NS_PER_HOUR
        if ctx.decision_time_utc >= due:
            return [Exit(pos.id, reason="time_exit")]
        return []


def scan_session_windows(md: MarketData, start, end, costs: CostModel | None = None,
                         account_units_per_usd: float = 1.0, hours=range(24), durations=range(1, 13),
                         sides=(1, -1), rollover_from_min: int = 1425, rollover_to_min: int = 75,
                         max_spread_points: float = 60.0, max_exec_delay_min: int = 59, min_obs: int = 30) -> dict:
    """EXPLORATORY scan of (h_in, h_out = h_in + d, side) windows on [start, end) ONLY.

    Each instance enters, like the engine, at the first M1 open inside the hour hh:00-hh:59 UTC
    that is outside the rollover window and has spread <= ``max_spread_points`` (0 disables;
    entry deadline = end of that H1 bar), at ask for longs / bid for shorts + slippage, and exits
    at the first M1 open at/after (hh + d):00 UTC (within ``max_exec_delay_min``); commission is
    deducted. Instances without a valid entry bar, with a late exit, or spanning a weekend are
    dropped. The protective stop of SESSION_DRIFT is NOT simulated here.

    Returns {"table": DataFrame (one row per window; mean/sd/t/p in points after costs,
    Holm-adjusted p), "best": row with the highest t-stat, "n_tried": windows with >= min_obs
    instances}.
    """
    from ..engine import in_minute_window
    from ..validation import holm_bonferroni

    costs = costs or CostModel()
    spec = md.spec
    s_ns, e_ns = to_ns(start), to_ns(end)
    j0, j1 = int(np.searchsorted(md.t, s_ns)), int(np.searchsorted(md.t, e_ns))
    if j1 - j0 < 100:
        raise ValueError("not enough data in the scan range")
    tu = md.t_utc[j0:j1]
    t = md.t[j0:j1]
    o = md.o[j0:j1]
    spr = costs.effective_spread_points(md.spread[j0:j1]) * spec.point
    ao = np.round(o + spr, spec.digits)
    slip = costs.slippage_points * spec.point
    comm_pts = costs.commission_per_lot_rt / (spec.contract_size * account_units_per_usd * spec.point)

    g0 = ((int(tu[0]) + NS_PER_HOUR - 1) // NS_PER_HOUR) * NS_PER_HOUR
    grid = np.arange(g0, int(tu[-1]) + 1, NS_PER_HOUR, dtype="int64")
    idx = np.searchsorted(tu, grid, "left")
    ok = idx < len(tu)
    idx_c = np.minimum(idx, len(tu) - 1)
    ok &= (tu[idx_c] - grid) <= max_exec_delay_min * NS_PER_MIN          # exit bars
    # entry bars: first bar in [hh:00, hh+1:00) outside the rollover window with spread <= cap
    valid = ~in_minute_window(t, rollover_from_min, rollover_to_min)
    if max_spread_points and max_spread_points > 0:
        valid &= costs.effective_spread_points(md.spread[j0:j1]) <= max_spread_points
    nxt = np.where(valid, np.arange(len(t)), len(t))
    nxt = np.minimum.accumulate(nxt[::-1])[::-1]                         # next valid index >= j
    ent = np.where(idx < len(tu), nxt[idx_c], len(t))
    end_h = np.searchsorted(tu, grid + NS_PER_HOUR, "left")
    entry_ok = ent < end_h
    ent_c = np.minimum(ent, len(t) - 1)
    hod = (grid % NS_PER_DAY) // NS_PER_HOUR
    rows = []
    for side in sides:
        for h in hours:
            ks = np.flatnonzero((hod == h) & entry_ok)
            for d in durations:
                ke = ks + d
                keep = ke < len(grid)
                a, b = ks[keep], ke[keep]
                keep2 = ok[b] & ((tu[idx_c[b]] - tu[ent_c[a]]) <= (d + 1) * NS_PER_HOUR)
                a, b = ent_c[a[keep2]], idx_c[b[keep2]]
                if side > 0:
                    ent, ex = ao[a] + slip, o[b] - slip
                else:
                    ent, ex = o[a] - slip, ao[b] + slip
                pts = side * (ex - ent) / spec.point - comm_pts
                n = len(pts)
                mean = float(pts.mean()) if n else np.nan
                sd = float(pts.std(ddof=1)) if n > 1 else np.nan
                tstat = mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else np.nan
                pval = float(sps.t.sf(tstat, n - 1)) if np.isfinite(tstat) else np.nan
                bps = float(np.mean(side * (ex - ent) / ent * 1e4 - comm_pts * spec.point / ent * 1e4)) if n else np.nan
                rows.append({"h_in": h, "h_out": (h + d) % 24, "duration_h": d, "side": side, "n": n,
                             "mean_pts": mean, "sd_pts": sd, "t_stat": tstat, "p_value": pval,
                             "mean_bps": bps, "win_rate": float((pts > 0).mean()) if n else np.nan})
    table = pd.DataFrame(rows)
    tried = table["n"] >= min_obs
    table["tried"] = tried
    table["p_holm"] = np.nan
    if tried.any():
        table.loc[tried, "p_holm"] = holm_bonferroni(table.loc[tried, "p_value"].fillna(1.0).to_numpy())["p_adjusted"]
    cand = table[tried & table["t_stat"].notna()]
    best = cand.sort_values("t_stat", ascending=False).iloc[0].to_dict() if len(cand) else None
    return {"table": table, "best": best, "n_tried": int(tried.sum()),
            "range": [str(pd.Timestamp(start)), str(pd.Timestamp(end))],
            "note": "exploratory: confirm any window on data not used by this scan"}
