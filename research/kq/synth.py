"""Synthetic gold-like M1 data (for tests and demos only — never for conclusions).

Model: GBM log-returns with Student-t(5) innovations, intraday volatility seasonality by
UTC hour (quiet Asia, London open, NY overlap peak), slowly varying volatility regimes
(AR(1) in log-vol), optional drift regimes, small gaps at each daily open and larger
weekend gaps. Bars follow HF Markets hours in server time (NY + 7h): Monday-Friday
01:00-23:59 (Friday until 23:54), daily break 00:00-01:00. Spreads (integer points) are
tight in liquid hours and widen strongly right after the daily open (rollover) and in the
last minutes before it. A few random minutes are missing.

CLI:  python -m kq.synth --start 2022-01-03 --end 2026-07-01 --seed 1 --out-dir DIR
writes DIR/KQ_XAUUSD_M1.csv (MT5 export format) and DIR/KQ_XAUUSD_spec.json.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .data import SymbolSpec
from .timeutil import NS_PER_DAY, NS_PER_HOUR, NS_PER_MIN, server_utc_offset_hours

# relative volatility by UTC hour (normalised below)
_UTC_HOUR_VOL = np.array([0.55, 0.50, 0.50, 0.55, 0.55, 0.60, 0.75, 1.30, 1.40, 1.15, 1.00, 0.95,
                          1.05, 1.60, 1.85, 1.60, 1.25, 1.00, 0.80, 0.70, 0.60, 0.55, 0.50, 0.50])
# base spread (points) by UTC hour
_UTC_HOUR_SPREAD = np.array([24, 26, 26, 25, 24, 22, 20, 17, 16, 16, 17, 17,
                             16, 15, 15, 16, 17, 18, 20, 22, 24, 30, 30, 26])


def generate_m1(start="2022-01-03", end="2026-07-01", seed: int = 0, s0: float = 1800.0,
                annual_vol: float = 0.16, drift_annual: float = 0.0, trend_regime_annual: float = 0.0,
                weekend_gap_sd: float = 0.004, daily_gap_sd: float = 0.0006, missing_frac: float = 0.002,
                vol_regime_sd: float = 0.12, vol_regime_phi: float = 0.97) -> pd.DataFrame:
    """Return an M1 DataFrame indexed by server time with MT5 export columns."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D",
                         inclusive="left")
    days = days[days.dayofweek < 5]
    if len(days) == 0:
        raise ValueError("no weekdays in range")
    day_ns = days.as_unit("ns").asi8
    minutes = np.arange(60, 1440, dtype="int64")               # 01:00 .. 23:59 server
    t = (day_ns[:, None] + minutes[None, :] * NS_PER_MIN)
    mask = np.ones(t.shape, dtype=bool)
    fri = days.dayofweek.to_numpy() == 4
    mask[np.ix_(fri, minutes >= 23 * 60 + 55)] = False         # Friday close 23:55
    first_min = np.zeros(t.shape, dtype=bool)
    first_min[:, 0] = True
    # drop a few random minutes (never the daily open)
    drop = (rng.random(t.shape) < missing_frac) & ~first_min
    mask &= ~drop
    t = t[mask]
    is_open = first_min[mask]
    day_idx = np.repeat(np.arange(len(days)), mask.sum(axis=1))
    n = len(t)

    # UTC hour via per-day server offset (constant during trading hours)
    off = server_utc_offset_hours(day_ns + 12 * NS_PER_HOUR).astype("int64")
    t_utc = t - off[day_idx] * NS_PER_HOUR
    hour_utc = (t_utc % NS_PER_DAY) // NS_PER_HOUR
    season = _UTC_HOUR_VOL / np.sqrt(np.mean(_UTC_HOUR_VOL ** 2))

    # daily volatility regime (AR(1) in log-vol) and optional drift regimes
    lv = np.zeros(len(days))
    eps = rng.normal(0, vol_regime_sd, len(days))
    for k in range(1, len(days)):
        lv[k] = vol_regime_phi * lv[k - 1] + eps[k]
    vol_day = np.exp(lv - lv.var() / 2)
    drift_day = np.zeros(len(days))
    if trend_regime_annual:
        state, k = 0, 0
        while k < len(days):
            length = int(rng.integers(20, 120))
            state = rng.choice([-1, 0, 1])
            drift_day[k:k + length] = state * trend_regime_annual
            k += length
    minutes_per_year = 252 * 23 * 60
    sigma = annual_vol / np.sqrt(minutes_per_year) * season[hour_utc] * vol_day[day_idx]
    mu = (drift_annual + drift_day[day_idx]) / minutes_per_year
    z = rng.standard_t(5, n) / np.sqrt(5 / 3)
    r = mu - 0.5 * sigma ** 2 + sigma * z
    gap = np.zeros(n)
    opens = np.flatnonzero(is_open)
    gap[opens] = rng.normal(0, daily_gap_sd, len(opens))
    monday = days.dayofweek.to_numpy()[day_idx[opens]] == 0
    gap[opens[monday]] = rng.normal(0, weekend_gap_sd, int(monday.sum()))
    gap[0] = 0.0
    logc = np.log(s0) + np.cumsum(gap + r)
    logo = logc - r
    close = np.exp(logc)
    open_ = np.exp(logo)
    wick = np.abs(rng.normal(0, 0.6, (2, n))) * sigma
    high = np.maximum(open_, close) * np.exp(wick[0])
    low = np.minimum(open_, close) * np.exp(-wick[1])
    open_, high, low, close = (np.round(x, 2) for x in (open_, high, low, close))
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])

    # spreads: base by UTC hour + noise, widening after the daily open and before the break
    mod = (t % NS_PER_DAY) // NS_PER_MIN
    spread = _UTC_HOUR_SPREAD[hour_utc] + rng.poisson(3, n)
    after_open = mod - 60
    widen = after_open < 20
    spread = np.where(widen, spread + (160 - 7 * np.clip(after_open, 0, 20)) + rng.integers(0, 60, n), spread)
    before_break = mod >= 23 * 60 + 50
    spread = np.where(before_break, spread + rng.integers(15, 45, n), spread)
    mon_open = widen & (days.dayofweek.to_numpy()[day_idx] == 0)
    spread = np.where(mon_open, spread + 60, spread)
    tick_volume = np.maximum(1, (40 * season[hour_utc] * (1 + np.abs(z)) + rng.poisson(5, n))).astype("int64")

    idx = pd.DatetimeIndex(t.view("datetime64[ns]"), name="time")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "tick_volume": tick_volume, "spread": spread.astype("int64"),
                         "real_volume": np.zeros(n, dtype="int64")}, index=idx)


def write_mt5_csv(df: pd.DataFrame, path, time_format: str = "mt5") -> None:
    """Write in the user's export format: time,open,...,real_volume with ``YYYY.MM.DD HH:MM``."""
    t = df.index.as_unit("ns").to_numpy()
    s = np.datetime_as_string(t, unit="m")                     # 2024-01-02T10:00
    s = pd.Series(s).str.replace("T", " ", regex=False)
    if time_format == "mt5":
        s = s.str.replace("-", ".", regex=False)
    out = pd.DataFrame({"time": s.to_numpy(), "open": df["open"].to_numpy(), "high": df["high"].to_numpy(),
                        "low": df["low"].to_numpy(), "close": df["close"].to_numpy(),
                        "tick_volume": df["tick_volume"].to_numpy(), "spread": df["spread"].to_numpy(),
                        "real_volume": df["real_volume"].to_numpy()})
    out.to_csv(path, index=False, float_format="%.2f")


def default_spec_dict(symbol: str = "XAUUSD", account_currency: str = "USD") -> dict:
    d = SymbolSpec(symbol=symbol, account_currency=account_currency, swap_long=-45.0, swap_short=20.0,
                   gmt_offset_seconds=None).to_dict()
    d.pop("gmt_offset_seconds")
    d["tick_value"] = 1.0
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate synthetic gold-like M1 data (MT5 export format)")
    ap.add_argument("--start", default="2022-01-03")
    ap.add_argument("--end", default="2026-07-01")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--s0", type=float, default=1800.0)
    ap.add_argument("--annual-vol", type=float, default=0.16)
    ap.add_argument("--drift", type=float, default=0.0)
    ap.add_argument("--trend-regime", type=float, default=0.0)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    df = generate_m1(a.start, a.end, seed=a.seed, s0=a.s0, annual_vol=a.annual_vol, drift_annual=a.drift,
                     trend_regime_annual=a.trend_regime)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv = out / f"KQ_{a.symbol}_M1.csv"
    spec = out / f"KQ_{a.symbol}_spec.json"
    write_mt5_csv(df, csv)
    with open(spec, "w") as f:
        json.dump(default_spec_dict(a.symbol), f, indent=2)
    print(json.dumps({"csv": str(csv), "spec": str(spec), "n_bars": int(len(df)),
                      "first": str(df.index[0]), "last": str(df.index[-1]),
                      "seconds": round(time.perf_counter() - t0, 2)}))


if __name__ == "__main__":
    main()
