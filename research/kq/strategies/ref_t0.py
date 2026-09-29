"""REF_T0 — the configuration currently live (MQL5/Presets/LIVE_H4_T0_tendencia.set).

Timeframe H4. EMA(40) and EMA(200) of close, ADX(14) (MT5 ADX.mq5), ATR(14) (MT5 ATR.mq5).
Long on closed bar i if
    EMA40 crosses above EMA200 between i-1 and i            (EMA40[i-1] <= EMA200[i-1] and EMA40[i] > EMA200[i])
 or EMA40[i] > EMA200[i] and close[i-1] <= EMA40[i-1] and close[i] > EMA40[i]   (pull-back)
Short symmetric. Entry only if ADX[i] >= adx_min. SL = 1.5 ATR[i], TP = 3 ATR[i] from the
quoted entry price. An opposite signal closes the open position (even if ADX is low) and
may open the new one. One position at a time; 1 % risk (set in BacktestConfig).
The EA waits inside the next bar while spread > 8 pips (80 points): ``max_spread_points``.
"""
from __future__ import annotations

import numpy as np

from ..indicators import adx_mt5, atr_mt5, ema
from .base import Strategy


class RefT0(Strategy):
    name = "REF_T0"
    default_params = {
        "timeframe": "H4",
        "fast": 40,
        "slow": 200,
        "entry_mode": "cross_pullback",   # or "cross_only" (EA entry mode 0)
        "adx_period": 14,
        "adx_min": 20.0,                  # 0 disables the filter
        "atr_period": 14,
        "sl_atr": 1.5,
        "tp_atr": 3.0,                    # 0 -> no take profit
        "close_on_opposite": True,
        "direction": "both",
        "max_spread_points": 80.0,        # EA InpMaxSpreadPips = 8 (pip = 0.1)
        "warmup_bars": None,              # None -> 3 * slow (EA: signals ignored while Bars() < 3 * slow)
    }

    def prepare(self, md):
        super().prepare(md)
        p = self.params
        c, h, l = self.b_close, self.b_high, self.b_low
        self.ema_f = ema(c, p["fast"])
        self.ema_s = ema(c, p["slow"])
        self.adx = adx_mt5(h, l, c, p["adx_period"])[0]
        self.atr = atr_mt5(h, l, c, p["atr_period"])
        f, s = self.ema_f, self.ema_s
        sig = np.zeros(len(c), dtype=np.int8)
        cu = np.zeros(len(c), bool)
        cd = np.zeros(len(c), bool)
        pu = np.zeros(len(c), bool)
        pdn = np.zeros(len(c), bool)
        cu[1:] = (f[:-1] <= s[:-1]) & (f[1:] > s[1:])
        cd[1:] = (f[:-1] >= s[:-1]) & (f[1:] < s[1:])
        if p["entry_mode"] == "cross_pullback":
            pu[1:] = (f[1:] > s[1:]) & (c[:-1] <= f[:-1]) & (c[1:] > f[1:])
            pdn[1:] = (f[1:] < s[1:]) & (c[:-1] >= f[:-1]) & (c[1:] < f[1:])
        elif p["entry_mode"] != "cross_only":
            raise ValueError("entry_mode must be 'cross_pullback' or 'cross_only'")
        # same precedence as the EA: crosses first, then pull-backs
        sig[pdn] = -1
        sig[pu] = 1
        sig[cd] = -1
        sig[cu] = 1
        self.sig = sig
        self._warm = self.warmup(3 * int(p["slow"]))

    def ready(self, i):
        # EA: g_warmingUp = Bars() < 3 * slow, and Bars() counts the forming bar -> i + 2 bars
        return i + 2 >= self._warm and np.isfinite(self.atr[i])

    def signal(self, i):
        return int(self.sig[i])

    def entry_block_reason(self, ctx, side):
        amin = float(self.params["adx_min"])
        if amin > 0:
            a = self.adx[ctx.i]
            if not np.isfinite(a) or a < amin:
                return f"adx_below_min({amin:g})"
        return None

    def stops(self, ctx, side):
        a = self.atr[ctx.i]
        if not np.isfinite(a) or a <= 0:
            return None
        tp = self.params["tp_atr"]
        return {"sl_dist": self.params["sl_atr"] * a, "tp_dist": tp * a if tp and tp > 0 else None}
