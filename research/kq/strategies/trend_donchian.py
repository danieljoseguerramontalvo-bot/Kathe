"""TREND_DONCHIAN — hypothesis: time-series momentum (breakout of the previous N-bar channel).

Timeframe H4 or D1. Long when close[i] > max(high[i-N .. i-1]); short when
close[i] < min(low[i-N .. i-1]). Initial SL = k_sl * ATR14[i] from the quoted entry price.
Chandelier trailing, updated only at TF bar closes and only tightening:
    long : stop = max(stop, HH - k_trail * ATR14[i]),  HH = highest HIGH of the TF bars that
           have CLOSED since the entry bar, entry bar included once it has closed;
    short: stop = min(stop, LL + k_trail * ATR14[i]),  LL = lowest LOW of the same bars.
ATR14[i] is the ATR of the last closed bar (MT5 ATR.mq5). The opposite breakout closes the
position and reverses. No take profit.
"""
from __future__ import annotations

import numpy as np

from ..indicators import atr_mt5, rolling_max_prev, rolling_min_prev
from .base import SetStop, Strategy


class TrendDonchian(Strategy):
    name = "TREND_DONCHIAN"
    default_params = {
        "timeframe": "H4",        # H4 or D1
        "n": 20,                  # 20 or 55
        "atr_period": 14,
        "k_sl": 2.0,
        "k_trail": 3.0,           # 0 disables the chandelier
        "close_on_opposite": True,
        "direction": "both",
        "max_spread_points": None,
        "warmup_bars": None,      # None -> max(n, atr_period) + 1
    }

    def prepare(self, md):
        super().prepare(md)
        p = self.params
        n = int(p["n"])
        self.atr = atr_mt5(self.b_high, self.b_low, self.b_close, p["atr_period"])
        self.hh = rolling_max_prev(self.b_high, n)
        self.ll = rolling_min_prev(self.b_low, n)
        c = self.b_close
        with np.errstate(invalid="ignore"):
            up = c > self.hh
            dn = c < self.ll
        self.sig = np.where(up, 1, np.where(dn, -1, 0)).astype(np.int8)
        self._warm = self.warmup(max(n, int(p["atr_period"])) + 1)

    def ready(self, i):
        return i >= self._warm and np.isfinite(self.atr[i])

    def signal(self, i):
        return int(self.sig[i])

    def stops(self, ctx, side):
        a = self.atr[ctx.i]
        if not np.isfinite(a) or a <= 0:
            return None
        return {"sl_dist": float(self.params["k_sl"]) * a}

    def chandelier_level(self, i: int, entry_bar: int, side: int) -> float:
        """Chandelier stop computed at the close of bar i (entry_bar <= i)."""
        k = float(self.params["k_trail"])
        if side > 0:
            return float(self.b_high[entry_bar:i + 1].max()) - k * self.atr[i]
        return float(self.b_low[entry_bar:i + 1].min()) + k * self.atr[i]

    def manage(self, ctx, pos):
        k = float(self.params["k_trail"])
        i = ctx.i
        if k <= 0 or not np.isfinite(self.atr[i]):
            return []
        eb = self.bar_index_of_m1(pos.entry_index)
        if eb > i:                     # entry bar not closed yet
            return []
        lvl = self.chandelier_level(i, eb, pos.side)
        if pos.stop is None or (pos.side > 0 and lvl > pos.stop) or (pos.side < 0 and lvl < pos.stop):
            return [SetStop(pos.id, lvl, "chandelier")]
        return []
