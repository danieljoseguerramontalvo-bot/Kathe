"""Indicators that reproduce MetaTrader 5 built-ins (arrays in chronological order).

Every value at index ``i`` uses only inputs at indices ``<= i`` (no look-ahead). Warm-up
values are NaN. Loops are written with the same arithmetic order as the MQL5 sources
(Custom Moving Average.mq5 / MovingAverages.mqh, ATR.mq5, RSI.mq5, ADX.mq5) so results
match the terminal to floating-point precision once the terminal has the same history.
"""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def _f(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def ema(x, n: int) -> np.ndarray:
    """MT5 iMA(MODE_EMA): alpha = 2/(n+1); first value = first price (first non-NaN input)."""
    x = _f(x)
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(~np.isnan(x))
    if len(valid) == 0:
        return out
    b = int(valid[0])
    a = 2.0 / (n + 1.0)
    xs = x.tolist()
    prev = xs[b]
    res = [prev]
    for v in xs[b + 1:]:
        prev = v * a + prev * (1.0 - a)
        res.append(prev)
    out[b:] = res
    return out


def sma(x, n: int) -> np.ndarray:
    """Simple moving average over the last n values (NaN for the first n-1)."""
    x = _f(x)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).mean(axis=1)
    return out


def true_range(high, low, close) -> np.ndarray:
    """TR[i] = max(high[i], close[i-1]) - min(low[i], close[i-1]); TR[0] = NaN (MT5 skips it)."""
    h, l, c = _f(high), _f(low), _f(close)
    tr = np.full(len(h), np.nan)
    if len(h) > 1:
        pc = c[:-1]
        tr[1:] = np.maximum(h[1:], pc) - np.minimum(l[1:], pc)
    return tr


def atr_mt5(high, low, close, n: int = 14) -> np.ndarray:
    """MT5 ATR.mq5: SIMPLE moving average of TR over n bars (not Wilder smoothing).

    ATR[n] = mean(TR[1..n]); ATR[i] = ATR[i-1] + (TR[i] - TR[i-n]) / n for i > n.
    Values for i < n are NaN.
    """
    tr = true_range(high, low, close)
    m = len(tr)
    out = np.full(m, np.nan)
    if m <= n:
        return out
    trl = tr.tolist()
    first = 0.0
    for i in range(1, n + 1):
        first += trl[i]
    prev = first / n
    res = [prev]
    for i in range(n + 1, m):
        prev = prev + (trl[i] - trl[i - n]) / n
        res.append(prev)
    out[n:] = res
    return out


def rsi_wilder(close, n: int = 14) -> np.ndarray:
    """MT5 RSI.mq5 (Wilder): seed = SMA of the first n gains/losses, then
    avg = (prev * (n-1) + x) / n. RSI = 100 - 100 / (1 + avg_gain/avg_loss); 100 if
    avg_loss == 0 and avg_gain > 0; 50 if both are 0. RSI[i] is NaN for i < n."""
    c = _f(close)
    m = len(c)
    out = np.full(m, np.nan)
    if m <= n:
        return out
    cl = c.tolist()
    sp = sn = 0.0
    for i in range(1, n + 1):
        d = cl[i] - cl[i - 1]
        sp += d if d > 0 else 0.0
        sn += -d if d < 0 else 0.0
    pos, neg = sp / n, sn / n

    def _rsi(p, q):
        if q != 0.0:
            return 100.0 - 100.0 / (1.0 + p / q)
        return 100.0 if p != 0.0 else 50.0

    res = [_rsi(pos, neg)]
    for i in range(n + 1, m):
        d = cl[i] - cl[i - 1]
        pos = (pos * (n - 1) + (d if d > 0.0 else 0.0)) / n
        neg = (neg * (n - 1) + (-d if d < 0.0 else 0.0)) / n
        res.append(_rsi(pos, neg))
    out[n:] = res
    return out


def adx_mt5(high, low, close, n: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MT5 ADX.mq5 (NOT the Wilder ADX / iADXWilder).

    Per bar: +DM = high - prev high, -DM = prev low - low (negatives -> 0); if +DM > -DM then
    -DM = 0; if -DM > +DM then +DM = 0; if equal both = 0. TR = max(high, prev close) -
    min(low, prev close). pdi = 100 * +DM / TR, ndi = 100 * -DM / TR (0 if TR == 0).
    +DI = EMA(pdi, n), -DI = EMA(ndi, n) with alpha = 2/(n+1); DX = 100 * |+DI - -DI| /
    (+DI + -DI) (0 if the sum is 0); ADX = EMA(DX, n).

    As in ADX.mq5 the three EMA buffers are 0 at bar 0 and the recursion starts at bar 1
    (ExponentialMA(i, n, prev, buffer)); the zero seed decays as (1-alpha)^i, so values are
    reliable after ~2n+ bars (MT5 itself draws from bar 2n). Returns (adx, +di, -di); bar 0
    is NaN.
    """
    h, l, c = _f(high), _f(low), _f(close)
    m = len(h)
    adx = np.full(m, np.nan)
    pdi_s = np.full(m, np.nan)
    ndi_s = np.full(m, np.nan)
    if m < 2:
        return adx, pdi_s, ndi_s
    a = 2.0 / (n + 1.0)
    hl, ll, cl = h.tolist(), l.tolist(), c.tolist()
    p_prev = q_prev = x_prev = 0.0
    r_adx, r_p, r_n = [], [], []
    for i in range(1, m):
        tmp_pos = hl[i] - hl[i - 1]
        tmp_neg = ll[i - 1] - ll[i]
        if tmp_pos < 0.0:
            tmp_pos = 0.0
        if tmp_neg < 0.0:
            tmp_neg = 0.0
        if tmp_pos > tmp_neg:
            tmp_neg = 0.0
        elif tmp_pos < tmp_neg:
            tmp_pos = 0.0
        else:
            tmp_pos = 0.0
            tmp_neg = 0.0
        tr = max(abs(hl[i] - ll[i]), abs(hl[i] - cl[i - 1]), abs(ll[i] - cl[i - 1]))
        if tr != 0.0:
            pd_ = 100.0 * tmp_pos / tr
            nd_ = 100.0 * tmp_neg / tr
        else:
            pd_ = nd_ = 0.0
        p_prev = pd_ * a + p_prev * (1.0 - a)
        q_prev = nd_ * a + q_prev * (1.0 - a)
        s = p_prev + q_prev
        dx = 100.0 * abs((p_prev - q_prev) / s) if s != 0.0 else 0.0
        x_prev = dx * a + x_prev * (1.0 - a)
        r_adx.append(x_prev)
        r_p.append(p_prev)
        r_n.append(q_prev)
    adx[1:] = r_adx
    pdi_s[1:] = r_p
    ndi_s[1:] = r_n
    return adx, pdi_s, ndi_s


def efficiency_ratio(close, n: int = 20) -> np.ndarray:
    """Kaufman Efficiency Ratio: |close[i] - close[i-n]| / sum_{k=i-n+1..i} |close[k]-close[k-1]|.
    NaN for i < n; 0 when the denominator is 0."""
    c = _f(close)
    m = len(c)
    out = np.full(m, np.nan)
    if m <= n:
        return out
    change = np.abs(c[n:] - c[:-n])
    absdiff = np.abs(np.diff(c))
    vol = sliding_window_view(absdiff, n).sum(axis=1)  # window ending at diff index i-1 -> bar i
    with np.errstate(invalid="ignore", divide="ignore"):
        er = np.where(vol > 0, change / vol, 0.0)
    out[n:] = er
    return out


def rolling_percentile_rank(x, window: int, min_periods: int | None = None) -> np.ndarray:
    """Past-only percentile rank in [0, 1] of x[i] among the PREVIOUS ``window`` values
    x[i-window .. i-1] (the current value is compared, not included):
    (count(prev < x[i]) + 0.5 * count(prev == x[i])) / count(valid prev).
    NaN when fewer than ``min_periods`` (default = window) valid previous values exist."""
    x = _f(x)
    m = len(x)
    out = np.full(m, np.nan)
    mp = window if min_periods is None else int(min_periods)
    if m <= 1:
        return out
    pad = np.concatenate([np.full(window, np.nan), x])
    win = sliding_window_view(pad[:-1], window)          # row i -> x[i-window .. i-1]
    cur = x[:, None]
    valid = ~np.isnan(win)
    less = np.sum((win < cur) & valid, axis=1)
    eq = np.sum((win == cur) & valid, axis=1)
    cnt = valid.sum(axis=1)
    ok = (cnt >= mp) & ~np.isnan(x)
    out[ok] = (less[ok] + 0.5 * eq[ok]) / cnt[ok]
    return out


def rolling_max_prev(x, n: int) -> np.ndarray:
    """max(x[i-n .. i-1]) — the previous n bars, excluding bar i. NaN for i < n."""
    x = _f(x)
    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = sliding_window_view(x[:-1], n).max(axis=1)
    return out


def rolling_min_prev(x, n: int) -> np.ndarray:
    """min(x[i-n .. i-1]) — the previous n bars, excluding bar i. NaN for i < n."""
    x = _f(x)
    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = sliding_window_view(x[:-1], n).min(axis=1)
    return out


def cross_above(a, b) -> np.ndarray:
    """True at i when a[i-1] <= b[i-1] and a[i] > b[i]."""
    a, b = _f(a), _f(b)
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[:-1] <= b[:-1]) & (a[1:] > b[1:])
    return out


def cross_below(a, b) -> np.ndarray:
    """True at i when a[i-1] >= b[i-1] and a[i] < b[i]."""
    a, b = _f(a), _f(b)
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[:-1] >= b[:-1]) & (a[1:] < b[1:])
    return out
