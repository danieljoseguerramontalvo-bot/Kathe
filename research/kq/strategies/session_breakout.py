"""SESSION_BREAKOUT — hypothesis: breakout after compression at the London/NY liquidity change.

Per UTC day:
* range = highest high / lowest low of the M1 bars in the range window (default 00:00-07:00
  UTC); the day is skipped when range width / ATR14(D1, last completed server day at the end
  of the range window) > ``c_max`` (``c_max=None`` -> no compression filter, the
  'unconditional' variant);
* entries on M5 closes whose bar opens inside the entry window (default 07:00-12:00 UTC):
  long if close > range_high + buffer, short if close < range_low - buffer, with
  buffer = ``buffer_frac`` * width; at most one entry attempt per day;
* SL = opposite side of the range (long SL = range low, triggered on bid; short SL = range
  high, triggered on ask); TP = ``tp_mult`` * width from the quoted entry (None = no TP);
* flat at ``flat_utc`` (default 20:00 UTC) at the latest.

Control (falsification): ``anchor_mode='random'`` replaces the range window, for every day,
by a random window of the SAME length that ends a random multiple of ``anchor_step_min``
minutes before the entry window starts, within the 24 h preceding it (seeded by
``anchor_seed``). Entry window, stop, target, buffer, filter and flat time are unchanged, and
the random window never overlaps the entry window, so the control has no look-ahead either.
``anchor_mode='fixed'`` is the real strategy (offset 0).

Decision times are only the M5 closes inside the entry window plus one decision per day at
``flat_utc`` (the engine resolves SL/TP on M1 in between), which keeps runs fast.
"""
from __future__ import annotations

import numpy as np

from ..indicators import atr_mt5
from ..timeutil import NS_PER_DAY, NS_PER_MIN, utc_to_server
from .base import Exit, Strategy, utc_minutes


class SessionBreakout(Strategy):
    name = "SESSION_BREAKOUT"
    default_params = {
        "timeframe": "M5",
        "range_start_utc": "00:00",
        "range_end_utc": "07:00",
        "entry_start_utc": "07:00",
        "entry_end_utc": "12:00",
        "flat_utc": "20:00",
        "buffer_frac": 0.1,
        "c_max": 0.4,               # None disables the compression filter
        "tp_mult": 2.0,             # 1, 2 or None
        "atr_period": 14,           # ATR on D1 server bars
        "min_range_m1_bars": 60,
        "direction": "both",
        "close_on_opposite": False,
        "max_spread_points": None,
        "anchor_mode": "fixed",     # 'fixed' (real) or 'random' (control)
        "anchor_seed": 0,
        "anchor_step_min": 15,
    }

    def prepare(self, md):
        super().prepare(md)
        p = self.params
        rs, re_ = utc_minutes(p["range_start_utc"]), utc_minutes(p["range_end_utc"])
        es, ee = utc_minutes(p["entry_start_utc"]), utc_minutes(p["entry_end_utc"])
        fl = utc_minutes(p["flat_utc"])
        if not (rs < re_ <= es < ee <= fl <= 1440):
            raise ValueError("need range_start < range_end <= entry_start < entry_end <= flat (UTC, same day)")
        if p["anchor_mode"] not in ("fixed", "random"):
            raise ValueError("anchor_mode must be 'fixed' or 'random'")
        self._flat_min = fl
        L = (re_ - rs) * NS_PER_MIN

        open_utc = self.bars["open_utc_ns"].to_numpy("int64")
        bday = open_utc // NS_PER_DAY
        bmod = (open_utc % NS_PER_DAY) // NS_PER_MIN
        in_entry = (bmod >= es) & (bmod < ee)
        days = np.unique(bday[in_entry])

        # ---- per-day range (M1), past-only by construction (window ends <= entry start)
        tu, h, l = md.t_utc, md.h, md.l
        d1 = md.bars("D1")
        atr_d1 = atr_mt5(d1["high"].to_numpy(float), d1["low"].to_numpy(float),
                         d1["close"].to_numpy(float), p["atr_period"])
        d1_close_utc = d1["close_utc_ns"].to_numpy("int64")
        rng = np.random.default_rng(p["anchor_seed"])
        step = int(p["anchor_step_min"]) * NS_PER_MIN
        max_steps = int((NS_PER_DAY - L) // step)
        n = len(days)
        self.day_rh = np.full(n, np.nan)
        self.day_rl = np.full(n, np.nan)
        self.day_ratio = np.full(n, np.nan)
        self.day_ws = np.zeros(n, dtype="int64")
        for k, d in enumerate(days.tolist()):
            E = d * NS_PER_DAY + es * NS_PER_MIN
            if p["anchor_mode"] == "fixed":
                ws, we = d * NS_PER_DAY + rs * NS_PER_MIN, d * NS_PER_DAY + re_ * NS_PER_MIN
            else:
                off = int(rng.integers(0, max_steps + 1)) * step
                we = E - off
                ws = we - L
            self.day_ws[k] = ws
            a, b = np.searchsorted(tu, ws, "left"), np.searchsorted(tu, we, "left")
            if b - a < int(p["min_range_m1_bars"]):
                continue
            rh, rl = float(h[a:b].max()), float(l[a:b].min())
            self.day_rh[k], self.day_rl[k] = rh, rl
            j = int(np.searchsorted(d1_close_utc, we, "right") - 1)
            if j >= 0 and np.isfinite(atr_d1[j]) and atr_d1[j] > 0:
                self.day_ratio[k] = (rh - rl) / atr_d1[j]
        self.days = days

        # ---- decisions: M5 closes in the entry window + one flat decision per day
        eb = np.flatnonzero(in_entry)
        t_entry = self.bars["close_time_ns"].to_numpy("int64")[eb]
        flat_utc = days * NS_PER_DAY + fl * NS_PER_MIN
        t_flat = utc_to_server(flat_utc)
        dec_t = np.concatenate([t_entry, t_flat])
        dec_bar = np.concatenate([eb, np.full(len(days), -1)])
        dec_day = np.concatenate([bday[eb], days])
        order = np.argsort(dec_t, kind="stable")
        self._dec_t = dec_t[order]
        self.dec_bar = dec_bar[order]
        self.dec_dayk = np.searchsorted(days, dec_day[order])
        self.traded = np.zeros(n, dtype=bool)

    def decision_times(self):
        return self._dec_t

    # ------------------------------------------------------------------ hooks
    def _day_ok(self, k) -> bool:
        return np.isfinite(self.day_rh[k]) and not self.traded[k]

    def signal(self, i):
        b = self.dec_bar[i]
        if b < 0:
            return 0
        k = self.dec_dayk[i]
        if not self._day_ok(k):
            return 0
        rh, rl = self.day_rh[k], self.day_rl[k]
        buf = float(self.params["buffer_frac"]) * (rh - rl)
        c = self.b_close[b]
        if c > rh + buf:
            return 1
        if c < rl - buf:
            return -1
        return 0

    def _compression_ok(self, k) -> bool:
        cmax = self.params["c_max"]
        return cmax is None or (np.isfinite(self.day_ratio[k]) and self.day_ratio[k] <= float(cmax))

    def entry_block_reason(self, ctx, side):
        k = self.dec_dayk[ctx.i]
        if not self._compression_ok(k):
            self.traded[k] = True          # skip the whole day
            return "compression_filter"
        return None

    def entry_window_ok(self, ctx):
        k = self.dec_dayk[ctx.i]
        return self.dec_bar[ctx.i] >= 0 and self._day_ok(k) and self._compression_ok(k)

    def on_enter(self, ctx, side):
        self.traded[self.dec_dayk[ctx.i]] = True

    def stops(self, ctx, side):
        k = self.dec_dayk[ctx.i]
        rh, rl = self.day_rh[k], self.day_rl[k]
        if not np.isfinite(rh):
            return None
        w = rh - rl
        m = self.params["tp_mult"]
        return {"sl_price": rl if side > 0 else rh, "tp_dist": float(m) * w if m else None}

    def manage(self, ctx, pos):
        flat = (pos.entry_time_utc // NS_PER_DAY) * NS_PER_DAY + self._flat_min * NS_PER_MIN
        if ctx.decision_time_utc >= flat:
            return [Exit(pos.id, reason="session_flat")]
        return []
