"""REF_RSI2 — Connors RSI(2) reversion (EA entry mode 2, the "+236 USD" report family).

Long if close[i] > EMA200[i] and RSI2[i] < 10; short if close[i] < EMA200[i] and RSI2[i] > 90.
Exit longs when RSI2 > 70 and shorts when RSI2 < 30 (checked at the bar close, executed at
the next M1 open). SL = 1.5 ATR14, TP = 6 ATR14 from the quoted entry price.
Optional: ADX(14) >= 20; H1 EMA200 trend filter read from the last CLOSED H1 bar (close vs
EMA of that same bar, as the EA); ATR trailing k * ATR (updated at bar closes, tighten only);
entry session and end-of-day close in server hours.
"""
from __future__ import annotations

import numpy as np

from ..data import last_closed_index
from ..indicators import adx_mt5, atr_mt5, ema, rsi_wilder
from ..timeutil import NS_PER_DAY, NS_PER_HOUR
from .base import Exit, SetStop, Strategy


class RefRsi2(Strategy):
    name = "REF_RSI2"
    default_params = {
        "timeframe": "M15",               # M15 or H4
        "ema_period": 200,
        "rsi_period": 2,
        "buy_level": 10.0,
        "sell_level": 90.0,
        "exit_long": 70.0,
        "exit_short": 30.0,
        "atr_period": 14,
        "sl_atr": 1.5,
        "tp_atr": 6.0,
        "adx_filter": False,
        "adx_period": 14,
        "adx_min": 20.0,
        "htf_filter": False,
        "htf_timeframe": "H1",
        "htf_period": 200,
        "trail_atr": 0.0,                 # e.g. 2.0; 0 disables
        "close_on_opposite": True,
        "direction": "both",
        "max_spread_points": 80.0,
        "session_start_hour": None,       # server hour, entries only in [start, end)
        "session_end_hour": None,
        "close_hour": None,               # server hour: flat at the first decision >= this hour
        "warmup_bars": None,              # None -> 3 * ema_period
    }

    def prepare(self, md):
        super().prepare(md)
        p = self.params
        c, h, l = self.b_close, self.b_high, self.b_low
        self.ema_s = ema(c, p["ema_period"])
        self.rsi = rsi_wilder(c, p["rsi_period"])
        self.atr = atr_mt5(h, l, c, p["atr_period"])
        self.adx = adx_mt5(h, l, c, p["adx_period"])[0] if p["adx_filter"] else None
        long_sig = (c > self.ema_s) & (self.rsi < p["buy_level"])
        short_sig = (c < self.ema_s) & (self.rsi > p["sell_level"])
        self.sig = np.where(long_sig, 1, np.where(short_sig, -1, 0)).astype(np.int8)
        if p["htf_filter"]:
            hb = md.bars(p["htf_timeframe"])
            hc = hb["close"].to_numpy(float)
            self.htf_close = hc
            self.htf_ema = ema(hc, p["htf_period"])
            self.htf_close_time = hb["close_time_ns"].to_numpy("int64")
            self.htf_min_index = 2 * int(p["htf_period"])
        self._warm = self.warmup(3 * int(p["ema_period"]))

    def ready(self, i):
        # same warm-up rule as the EA (Bars() incl. the forming bar >= 3 * ema_period)
        return i + 2 >= self._warm and np.isfinite(self.atr[i]) and np.isfinite(self.rsi[i])

    def signal(self, i):
        return int(self.sig[i])

    def _hour(self, ns):
        return int((ns % NS_PER_DAY) // NS_PER_HOUR)

    def entry_block_reason(self, ctx, side):
        p = self.params
        if p["session_start_hour"] is not None and p["session_end_hour"] is not None:
            hr = self._hour(ctx.exec_time)
            if not (int(p["session_start_hour"]) <= hr < int(p["session_end_hour"])):
                return "outside_session"
        if p["close_hour"] is not None and self._hour(ctx.exec_time) >= int(p["close_hour"]):
            return "after_close_hour"
        if p["adx_filter"]:
            a = self.adx[ctx.i]
            if not np.isfinite(a) or a < float(p["adx_min"]):
                return f"adx_below_min({float(p['adx_min']):g})"
        if p["htf_filter"]:
            k = int(last_closed_index(self.htf_close_time, ctx.decision_time))
            if k < self.htf_min_index:
                return "htf_warmup"
            trend = np.sign(self.htf_close[k] - self.htf_ema[k])
            if trend != side:
                return "htf_trend_against"
        return None

    def entry_window_ok(self, ctx):
        p = self.params
        if p["session_start_hour"] is not None and p["session_end_hour"] is not None:
            hr = self._hour(ctx.exec_time)
            return int(p["session_start_hour"]) <= hr < int(p["session_end_hour"])
        return True

    def stops(self, ctx, side):
        a = self.atr[ctx.i]
        if not np.isfinite(a) or a <= 0:
            return None
        tp = self.params["tp_atr"]
        return {"sl_dist": self.params["sl_atr"] * a, "tp_dist": tp * a if tp and tp > 0 else None}

    def manage(self, ctx, pos):
        p, i = self.params, ctx.i
        acts = []
        if p["close_hour"] is not None:
            same_day = ctx.decision_time // NS_PER_DAY == pos.entry_time // NS_PER_DAY
            if (not same_day) or self._hour(ctx.decision_time) >= int(p["close_hour"]):
                return [Exit(pos.id, reason="end_of_day")]
        if pos.side > 0 and self.rsi[i] > p["exit_long"]:
            return [Exit(pos.id, reason="rsi_exit")]
        if pos.side < 0 and self.rsi[i] < p["exit_short"]:
            return [Exit(pos.id, reason="rsi_exit")]
        k = float(p["trail_atr"] or 0.0)
        if k > 0 and np.isfinite(self.atr[i]):
            if pos.side > 0:
                new = self.b_close[i] - k * self.atr[i]
                if pos.stop is None or new > pos.stop:
                    acts.append(SetStop(pos.id, new, "atr_trail"))
            else:
                ask_close = self.b_close[i] + self.b_spread[i] * self.md.spec.point
                new = ask_close + k * self.atr[i]
                if pos.stop is None or new < pos.stop:
                    acts.append(SetStop(pos.id, new, "atr_trail"))
        return acts
