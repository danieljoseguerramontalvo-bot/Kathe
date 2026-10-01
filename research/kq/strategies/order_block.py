"""ORDER_BLOCK — order blocks (SMC/ICT) en una versión mecánica, sin mirar al futuro.

No hay una definición única de «order block»; esta es una traducción explícita para poder probarla:

1. **Estructura.** Un máximo de swing es un fractal de ``swing_w`` velas a cada lado y solo se
   conoce ``swing_w`` velas después (igual para los mínimos).
2. **Ruptura de estructura (BOS) con desplazamiento.** Al cierre de la vela i, si cierra por encima
   del último máximo de swing confirmado (y aún no roto), y el impulso desde el mínimo del order block
   hasta ese cierre mide al menos ``disp_atr`` × ATR, se crea un **order block alcista**: la última vela
   bajista (cierre < apertura) de las ``lookback`` anteriores. Zona = [mínimo, máximo] de esa vela.
   Simétrico para el bajista (ruptura de un mínimo; última vela alcista).
3. **Entrada en la primera vuelta a la zona** (mitigación): al cierre de una vela posterior que toca
   la zona (mínimo ≤ techo de la zona alcista) sin cerrar por debajo de su suelo y cerrando como mucho
   ``near_atr`` × ATR por encima del techo (para no comprar lejos de la zona). Se entra a mercado al
   abrir la siguiente vela de 1 minuto. Cada zona se usa una sola vez y caduca a las ``max_age_bars``
   velas; un cierre al otro lado de la zona la invalida.
4. **Stop** al otro lado de la zona más ``sl_buffer_atr`` × ATR. **Objetivo** a ``rr`` veces el riesgo,
   medido desde el precio de entrada. Si la siguiente vela de 1 minuto llega más de ``max_exec_delay_min``
   minutos tarde (pausa diaria, fin de semana), no se entra.
   **Salida por tiempo** a las ``max_hold_bars`` velas. Sin entradas el viernes desde las
   ``friday_cutoff_utc`` (para no quedar abiertos el fin de semana).

Es una hipótesis del usuario, sin evidencia publicada que la respalde: se usa en modo señales
(validación prospectiva) hasta que su registro lo justifique.
"""
from __future__ import annotations

import numpy as np

from ..indicators import atr_mt5
from ..timeutil import server_to_utc, weekday_of_ns
from .base import Exit, Strategy

NS_PER_HOUR = 3_600_000_000_000
NS_PER_MIN = 60_000_000_000


def order_block_signals(o, h, l, c, atr, swing_w=3, lookback=10, disp_atr=1.5, max_age_bars=96,
                        near_atr=0.5, sl_buffer_atr=0.1):
    """Señal (+1/−1/0), stop y zona por vela, usando en cada vela i solo velas ≤ i."""
    n = len(c)
    sig = np.zeros(n, dtype=np.int8)
    stop = np.full(n, np.nan)
    ztop = np.full(n, np.nan)
    zbot = np.full(n, np.nan)
    last_sh = last_sl = np.nan
    sh_broken = sl_broken = True
    zones = {1: None, -1: None}           # (top, bottom, created_index)
    w = int(swing_w)
    for i in range(n):
        k = i - w                         # el swing en k se confirma al cerrar i = k + w
        if k - w >= 0:
            if h[k] > h[k - w:k].max() and h[k] >= h[k + 1:i + 1].max():
                last_sh, sh_broken = h[k], False
            if l[k] < l[k - w:k].min() and l[k] <= l[k + 1:i + 1].min():
                last_sl, sl_broken = l[k], False
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        # 1) entradas en zonas creadas antes de i
        for side in (1, -1):
            z = zones[side]
            if z is None:
                continue
            top, bot, created = z
            if i - created > max_age_bars:
                zones[side] = None
                continue
            if side > 0:
                if c[i] < bot:
                    zones[side] = None                    # invalidada
                elif l[i] <= top:
                    zones[side] = None                    # mitigada: solo la primera vuelta
                    sl = bot - sl_buffer_atr * a
                    if sig[i] == 0 and c[i] <= top + near_atr * a and sl < c[i]:
                        sig[i], stop[i], ztop[i], zbot[i] = 1, sl, top, bot
            else:
                if c[i] > top:
                    zones[side] = None
                elif h[i] >= bot:
                    zones[side] = None
                    sl = top + sl_buffer_atr * a
                    if sig[i] == 0 and c[i] >= bot - near_atr * a and sl > c[i]:
                        sig[i], stop[i], ztop[i], zbot[i] = -1, sl, top, bot
        # 2) nuevas zonas por ruptura de estructura con desplazamiento
        if np.isfinite(last_sh) and not sh_broken and c[i] > last_sh:
            sh_broken = True
            for j in range(i - 1, max(i - lookback, 0) - 1, -1):
                if c[j] < o[j]:
                    if c[i] - l[j] >= disp_atr * a:
                        zones[1] = (h[j], l[j], i)
                    break
        if np.isfinite(last_sl) and not sl_broken and c[i] < last_sl:
            sl_broken = True
            for j in range(i - 1, max(i - lookback, 0) - 1, -1):
                if c[j] > o[j]:
                    if h[j] - c[i] >= disp_atr * a:
                        zones[-1] = (h[j], l[j], i)
                    break
    return sig, stop, ztop, zbot


class OrderBlock(Strategy):
    name = "ORDER_BLOCK"
    default_params = {
        "timeframe": "M15",
        "swing_w": 3,
        "lookback": 10,
        "disp_atr": 1.5,
        "max_age_bars": 96,       # 24 h en M15
        "near_atr": 0.5,
        "sl_buffer_atr": 0.1,
        "rr": 2.0,
        "min_sl_atr": 0.25,       # stop mínimo (× ATR): con zonas diminutas el coste se comería el objetivo
        "max_hold_bars": 32,      # 8 h en M15
        "atr_period": 14,
        "friday_cutoff_utc": 16,  # sin entradas el viernes desde esta hora UTC
        "max_exec_delay_min": 2,  # si el mercado no abre en esos minutos (pausa, fin de semana) no se entra
        "direction": "both",
        "close_on_opposite": False,
        "max_spread_points": None,
        "warmup_bars": None,
    }

    def prepare(self, md):
        super().prepare(md)
        p = self.params
        self.atr = atr_mt5(self.b_high, self.b_low, self.b_close, p["atr_period"])
        self.sig, self.stop, self.ztop, self.zbot = order_block_signals(
            self.b_open, self.b_high, self.b_low, self.b_close, self.atr, int(p["swing_w"]), int(p["lookback"]),
            float(p["disp_atr"]), int(p["max_age_bars"]), float(p["near_atr"]), float(p["sl_buffer_atr"]))
        self.close_utc = server_to_utc(self.bars["close_time_ns"].to_numpy(dtype="int64"))
        self._warm = self.warmup(int(p["atr_period"]) + 2 * int(p["swing_w"]) + 1)

    def ready(self, i):
        return i >= self._warm

    def signal(self, i):
        return int(self.sig[i])

    def entry_block_reason(self, ctx, side):
        if ctx.exec_time - ctx.decision_time > int(self.params["max_exec_delay_min"]) * NS_PER_MIN:
            return "market_closed_at_decision"
        cut = self.params["friday_cutoff_utc"]
        t = int(self.close_utc[ctx.i])
        if cut is not None and int(weekday_of_ns(np.array([t]))[0]) == 4 and (t % (24 * NS_PER_HOUR)) // NS_PER_HOUR >= int(cut):
            return "friday_cutoff"
        return None

    def stops(self, ctx, side):
        sl = self.stop[ctx.i]
        if not np.isfinite(sl):
            return None
        ref = self.b_close[ctx.i]
        floor = float(self.params["min_sl_atr"]) * self.atr[ctx.i]
        if abs(ref - sl) < floor:
            sl = ref - side * floor
        risk = abs(ref - sl)
        if risk <= 0:
            return None
        # stop en el nivel de la zona; objetivo medido desde el precio real de entrada
        return {"sl_price": float(sl), "tp_dist": float(self.params["rr"]) * risk}

    def manage(self, ctx, pos):
        eb = self.bar_index_of_m1(pos.entry_index)
        if ctx.i - eb >= int(self.params["max_hold_bars"]):
            return [Exit(pos.id, reason="time_exit")]
        return []
