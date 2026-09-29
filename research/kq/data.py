"""Market data: MT5 CSV/spec loaders, validation, resampling and the MarketData container.

Conventions
-----------
* Prices are MT5 BID prices. Ask = Bid + spread * point, with the spread (in points) of
  the same M1 bar.
* Times are naive *server* times (HF Markets: New York + 7h), stored as int64 ns.
* Higher-timeframe bars are labelled by their OPEN time in server time. H4 bars start at
  00, 04, 08, ... and D1 bars at 00:00 server. A bar opening at ``t`` with length ``L``
  is complete (closed) at ``t + L``.
"""
from __future__ import annotations

import hashlib
import json
import re
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .timeutil import NS_PER_DAY, NS_PER_MIN, server_to_utc, to_ns

TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

PRICE_COLS = ["open", "high", "low", "close"]
MT5_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]


def tf_ns(tf: str) -> int:
    """Length of a timeframe in nanoseconds."""
    try:
        return TF_MINUTES[tf.upper()] * NS_PER_MIN
    except KeyError as exc:
        raise ValueError(f"unknown timeframe {tf!r}; use one of {list(TF_MINUTES)}") from exc


# --------------------------------------------------------------------------------------
# Symbol specification
# --------------------------------------------------------------------------------------
_SWAP_MODE_INT = {0: "disabled", 1: "points", 4: "money"}


@dataclass
class SymbolSpec:
    """Contract specification. Defaults are HF Markets XAUUSD."""

    symbol: str = "XAUUSD"
    digits: int = 2
    point: float = 0.01
    tick_size: float = 0.01
    tick_value: float = 1.0          # USD per tick per 1.0 lot (0.01 * 100)
    contract_size: float = 100.0     # oz per lot -> USD per 1.0 price move per lot
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    stops_level: int = 0             # points
    swap_long: float = 0.0           # per lot per night, unit given by swap_mode
    swap_short: float = 0.0
    swap_3days: int = 3              # MT5 ENUM_DAY_OF_WEEK: 0=Sunday ... 3=Wednesday
    swap_mode: str = "points"        # "points" | "money" (account currency) | "disabled"
    account_currency: str = "USD"
    gmt_offset_seconds: int | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "SymbolSpec":
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        kwargs, extra = {}, {}
        for k, v in d.items():
            key = k.strip().lower()
            if key in known:
                kwargs[key] = v
            else:
                extra[key] = v
        spec = cls(**kwargs)
        spec.extra = extra
        # type coercion (MT5 scripts may write numbers as strings)
        for name in ("digits", "stops_level", "swap_3days"):
            setattr(spec, name, int(float(getattr(spec, name))))
        for name in ("point", "tick_size", "tick_value", "contract_size", "volume_min",
                     "volume_max", "volume_step", "swap_long", "swap_short"):
            setattr(spec, name, float(getattr(spec, name)))
        if isinstance(spec.swap_mode, (int, float)) or str(spec.swap_mode).isdigit():
            code = int(spec.swap_mode)
            if code not in _SWAP_MODE_INT:
                raise ValueError(f"swap_mode {code} (MT5 ENUM_SYMBOL_SWAP_MODE) is not supported: only 0 (disabled), "
                                 f"1 (points) and 4 (account currency); pass the swap explicitly or disable it")
            spec.swap_mode = _SWAP_MODE_INT[code]
        spec.swap_mode = str(spec.swap_mode).lower()
        if spec.gmt_offset_seconds is not None:
            spec.gmt_offset_seconds = int(float(spec.gmt_offset_seconds))
        return spec

    @classmethod
    def from_json(cls, path) -> "SymbolSpec":
        with open(path, "r", encoding=_detect_encoding(path)) as f:
            return cls.from_dict(json.load(f))

    def to_dict(self) -> dict:
        d = asdict(self)
        extra = d.pop("extra")
        d.update({f"extra.{k}": v for k, v in extra.items()})
        return d

    def default_units_per_usd(self) -> float:
        """100 for cent accounts (USC), else 1."""
        return 100.0 if self.account_currency.strip().upper() in ("USC", "USCENT", "US CENT") else 1.0

    def money_per_lot_check(self, units_per_usd: float, tol: float = 1e-3) -> dict:
        """Compare the value the engine assumes for a 1.0 price move on 1.0 lot
        (contract_size x units_per_usd, account currency) with what the broker reports:
        ``money_per_price_unit_per_lot`` from the audit script (OrderCalcProfit), else
        tick_value / tick_size. ``ok`` is False when they differ by more than ``tol``."""
        expected = float(self.contract_size) * float(units_per_usd)
        observed, source = None, None
        v = self.extra.get("money_per_price_unit_per_lot")
        try:
            if v is not None and float(v) > 0:
                observed, source = float(v), "money_per_price_unit_per_lot"
        except (TypeError, ValueError):
            pass
        if observed is None and self.tick_size > 0 and self.tick_value > 0:
            observed, source = self.tick_value / self.tick_size, "tick_value/tick_size"
        ok = observed is None or abs(observed / expected - 1.0) <= tol
        return {"expected": expected, "observed": observed, "source": source, "ok": bool(ok)}

    def server_offset_check(self) -> dict:
        """Check the NY+7 server-time assumption against the audit's GMT offset
        (``gmt_offset_seconds`` measured at ``export_time_server``)."""
        from .timeutil import server_utc_offset_hours
        t = self.extra.get("export_time_server")
        if self.gmt_offset_seconds is None or not t:
            return {"checked": False, "ok": True}
        try:
            ts = pd.Timestamp(str(t).replace(".", "-", 2))
        except (ValueError, TypeError):
            return {"checked": False, "ok": True}
        exp = server_utc_offset_hours(ts) * 3600.0
        # the audit rounds TimeTradeServer - TimeGMT; allow a few minutes of clock skew
        return {"checked": True, "expected_seconds": exp, "observed_seconds": self.gmt_offset_seconds,
                "ok": bool(abs(exp - self.gmt_offset_seconds) <= 300)}


def load_spec(path=None, **overrides) -> SymbolSpec:
    """Load ``KQ_<SYMBOL>_spec.json`` if given/existing; defaults to XAUUSD otherwise."""
    if path is not None and Path(path).exists():
        spec = SymbolSpec.from_json(path)
    else:
        if path is not None:
            warnings.warn(f"spec file {path} not found; using XAUUSD defaults")
        spec = SymbolSpec()
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec


# --------------------------------------------------------------------------------------
# CSV loader
# --------------------------------------------------------------------------------------
def _detect_encoding(path) -> str:
    with open(path, "rb") as f:
        head = f.read(4)
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16"
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "utf-8"


_TIME_FORMATS = [
    (re.compile(r"^\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}$"), "%Y.%m.%d %H:%M"),
    (re.compile(r"^\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}$"), "%Y.%m.%d %H:%M:%S"),
    (re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"), "%Y-%m-%d %H:%M"),
    (re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"), "%Y-%m-%d %H:%M:%S"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$"), "ISO8601"),
]


def parse_server_times(values) -> pd.DatetimeIndex:
    """Parse MT5 time strings: ``YYYY.MM.DD HH:MM`` or ``YYYY-MM-DD HH:MM[:SS]``."""
    s = pd.Series(values).astype(str).str.strip()
    if len(s) == 0:
        return pd.DatetimeIndex([], dtype="datetime64[ns]")
    first = s.iloc[0]
    fmt = next((f for rx, f in _TIME_FORMATS if rx.match(first)), None)
    try:
        if fmt is None:
            raise ValueError
        out = pd.to_datetime(s, format=fmt)
    except (ValueError, TypeError):
        # mixed formats: normalise the date separator and let pandas infer each row
        s2 = s.str.replace(r"^(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", regex=True)
        out = pd.to_datetime(s2, format="mixed")
    return pd.DatetimeIndex(out).as_unit("ns")


def _read_frame(path) -> pd.DataFrame:
    enc = _detect_encoding(path)
    with open(path, "r", encoding=enc) as f:
        header = f.readline()
    sep = "\t" if "\t" in header else (";" if header.count(";") > header.count(",") else ",")
    names = [c.strip().strip("<>").lower() for c in header.strip().split(sep)]
    raw_names = [c.strip() for c in header.strip().split(sep)]
    text_cols = {rn for rn, nm in zip(raw_names, names) if nm in ("time", "date")}
    try:   # fast path: numeric columns parsed by the C reader
        df = pd.read_csv(path, sep=sep, encoding=enc, skipinitialspace=True,
                         dtype={c: str for c in text_cols} | {c: "float64" for c in raw_names if c not in text_cols})
    except (ValueError, TypeError):
        df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str, skipinitialspace=True)
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]
    # MT5 "Export bars" format: <DATE> <TIME> <OPEN> ... <TICKVOL> <VOL> <SPREAD>
    if "date" in df.columns and "time" not in df.columns:
        raise ValueError("CSV has a 'date' column but no 'time' column")
    if "date" in df.columns and "time" in df.columns:
        df["time"] = df["date"].str.strip() + " " + df["time"].str.strip()
        df = df.drop(columns=["date"])
    df = df.rename(columns={"tickvol": "tick_volume", "vol": "real_volume", "volume": "real_volume"})
    missing = {"time", "open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"CSV {path} is missing columns {sorted(missing)}; got {list(df.columns)}")
    return df


def load_mt5_csv(path, start=None, end=None, repair: bool = True, return_report: bool = False):
    """Load ``KQ_<SYMBOL>_M1.csv`` exported from MT5.

    Header ``time,open,high,low,close,tick_volume,spread,real_volume``; ``time`` in server
    time (``YYYY.MM.DD HH:MM`` or ``YYYY-MM-DD HH:MM[:SS]``); ``spread`` in integer points.
    Also accepts the MT5 "Export bars" format (``<DATE> <TIME> ...``), ``;``/tab separators
    and UTF-16 files.

    Rows are sorted by time, duplicate timestamps keep the last row, rows with missing or
    non-positive prices are dropped. With ``repair=True`` inconsistent OHLC rows are fixed
    (high = max(o,h,l,c), low = min(o,h,l,c)). ``start``/``end`` (server time, end exclusive)
    optionally restrict the loaded range. Returns a DataFrame indexed by server time
    (and the data-quality report if ``return_report``).
    """
    raw = _read_frame(path)
    report = {"path": str(path), "rows_read": int(len(raw))}
    idx = parse_server_times(raw["time"])
    df = pd.DataFrame(index=idx)
    df.index.name = "time"
    def _num(col):
        v = raw[col]
        return v.to_numpy(dtype=float) if v.dtype.kind == "f" else pd.to_numeric(v.to_numpy(), errors="coerce")
    for c in PRICE_COLS:
        df[c] = _num(c)
    if "spread" not in raw.columns:
        raise ValueError(f"{path}: no 'spread' column. Costs cannot be modelled without the bar spread; "
                         "export with Scripts/KQ_ExportarHistorial.mq5")
    for c, default in (("tick_volume", 0.0), ("spread", np.nan), ("real_volume", 0.0)):
        df[c] = _num(c) if c in raw.columns else default
    n_nospread = int(df["spread"].isna().sum())
    report["rows_missing_spread"] = n_nospread
    if n_nospread:
        warnings.warn(f"{n_nospread} rows without spread; filled with the median spread")
        med = df["spread"].median()
        df["spread"] = df["spread"].fillna(0.0 if np.isnan(med) else med)

    bad_price = df[PRICE_COLS].isna().any(axis=1) | (df[PRICE_COLS] <= 0).any(axis=1)
    report["rows_bad_price_dropped"] = int(bad_price.sum())
    df = df[~bad_price]
    report["non_monotonic_input"] = bool(not df.index.is_monotonic_increasing)
    df = df.sort_index(kind="stable")
    dup = df.index.duplicated(keep="last")
    report["duplicates_dropped"] = int(dup.sum())
    df = df[~dup]

    o, h, l, c = (df[x].to_numpy() for x in PRICE_COLS)
    bad_ohlc = (h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l)
    report["rows_bad_ohlc"] = int(bad_ohlc.sum())
    if repair and bad_ohlc.any():
        hi = np.max(np.vstack([o, h, l, c]), axis=0)
        lo = np.min(np.vstack([o, h, l, c]), axis=0)
        df["high"], df["low"] = hi, lo

    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.index < pd.Timestamp(end)]
    df["spread"] = df["spread"].astype("float64")
    report.update(bar_report(df))
    return (df, report) if return_report else df


def bar_report(df: pd.DataFrame) -> dict:
    """Basic data-quality statistics for an M1 frame."""
    if len(df) == 0:
        return {"n_bars": 0}
    t = df.index.as_unit("ns").asi8
    gaps = np.diff(t) / NS_PER_MIN
    wd = df.index.dayofweek
    return {
        "n_bars": int(len(df)),
        "first_bar": str(df.index[0]),
        "last_bar": str(df.index[-1]),
        "weekend_bars": int(((wd == 5) | (wd == 6)).sum()),
        "gaps_over_5min_not_weekend_or_break": int(((gaps > 5) & (gaps < 60)).sum()),
        "gaps_1h_to_1d": int(((gaps >= 60) & (gaps < 24 * 60)).sum()),
        "spread_median_points": float(np.median(df["spread"].to_numpy())),
        "spread_p99_points": float(np.percentile(df["spread"].to_numpy(), 99)),
        "share_spread_le_1_point": float(np.mean(df["spread"].to_numpy() <= 1.0)),
    }


def file_sha256(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# Resampling
# --------------------------------------------------------------------------------------
def resample_arrays(t_ns, o, h, l, c, spread, vol, tf: str) -> dict:
    """Aggregate sorted M1 arrays into ``tf`` bars labelled by open time (server time)."""
    L = tf_ns(tf)
    t_ns = np.asarray(t_ns, dtype="int64")
    n = len(t_ns)
    if n == 0:
        raise ValueError("no bars to resample")
    b = np.floor_divide(t_ns, L)  # epoch-aligned: H4 -> 00,04,...; D1 -> 00:00 server
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    ends = np.r_[starts[1:], n]
    cnt = ends - starts
    out = {
        "time": b[starts] * L,
        "open": o[starts],
        "high": np.maximum.reduceat(h, starts),
        "low": np.minimum.reduceat(l, starts),
        "close": c[ends - 1],
        "tick_volume": np.add.reduceat(vol, starts),
        "spread": spread[ends - 1],                      # spread of the last M1 bar
        "spread_mean": np.add.reduceat(spread, starts) / cnt,
        "m1_start": starts,
        "m1_end": ends,
        "n_m1": cnt,
    }
    out["close_time"] = out["time"] + L
    return out


def resample_bars(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample an M1 DataFrame (indexed by server time) to ``tf``."""
    t = m1.index.as_unit("ns").asi8
    arr = resample_arrays(t, m1["open"].to_numpy(float), m1["high"].to_numpy(float),
                          m1["low"].to_numpy(float), m1["close"].to_numpy(float),
                          m1["spread"].to_numpy(float), m1["tick_volume"].to_numpy(float), tf)
    return _bars_frame(arr)


def _bars_frame(arr: dict) -> pd.DataFrame:
    idx = pd.DatetimeIndex(arr["time"].view("datetime64[ns]"), name="time")
    cols = {k: v for k, v in arr.items() if k not in ("time", "close_time")}
    df = pd.DataFrame(cols, index=idx)
    df["close_time_ns"] = np.asarray(arr["close_time"], dtype="int64")      # server, ns
    df["open_utc_ns"] = server_to_utc(np.asarray(arr["time"], dtype="int64"))
    df["close_utc_ns"] = server_to_utc(np.asarray(arr["close_time"], dtype="int64"))
    return df


# --------------------------------------------------------------------------------------
# MarketData container
# --------------------------------------------------------------------------------------
class MarketData:
    """M1 bid bars + spread (the resolution used for fills/exits) and cached resampled bars."""

    def __init__(self, m1: pd.DataFrame, spec: SymbolSpec | None = None, source: dict | None = None):
        if not m1.index.is_monotonic_increasing or m1.index.has_duplicates:
            raise ValueError("M1 index must be strictly increasing (use load_mt5_csv)")
        m1 = m1.copy()
        m1.index = pd.DatetimeIndex(m1.index).as_unit("ns")
        if "tick_volume" not in m1.columns:
            m1["tick_volume"] = 0.0
        if "spread" not in m1.columns:
            m1["spread"] = 0.0
        self.m1 = m1
        self.spec = spec or SymbolSpec()
        self.source = dict(source or {})
        self.t = m1.index.asi8.copy()
        self.o = m1["open"].to_numpy(dtype=float).copy()
        self.h = m1["high"].to_numpy(dtype=float).copy()
        self.l = m1["low"].to_numpy(dtype=float).copy()
        self.c = m1["close"].to_numpy(dtype=float).copy()
        self.spread = m1["spread"].to_numpy(dtype=float).copy()
        self.vol = m1["tick_volume"].to_numpy(dtype=float).copy()
        self.t_utc = server_to_utc(self.t)          # int64 ns, naive UTC
        self._bars: dict[str, pd.DataFrame] = {}

    # ---- constructors --------------------------------------------------------------
    @classmethod
    def from_csv(cls, path, spec_path=None, start=None, end=None, **spec_overrides) -> "MarketData":
        df, report = load_mt5_csv(path, start=start, end=end, return_report=True)
        spec = load_spec(spec_path, **spec_overrides)
        source = {"path": str(Path(path).resolve()), "sha256": file_sha256(path),
                  "spec_path": str(Path(spec_path).resolve()) if spec_path else None,
                  "spec_sha256": file_sha256(spec_path) if spec_path and Path(spec_path).exists() else None,
                  "quality": report}
        return cls(df, spec, source)

    # ---- accessors -----------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.t)

    @property
    def first_time(self) -> pd.Timestamp:
        return pd.Timestamp(int(self.t[0]), unit="ns")

    @property
    def last_time(self) -> pd.Timestamp:
        return pd.Timestamp(int(self.t[-1]), unit="ns")

    def bars(self, tf: str) -> pd.DataFrame:
        """Resampled bars (cached). Columns: open, high, low, close, tick_volume, spread
        (last M1 spread), spread_mean, m1_start, m1_end, n_m1, close_time_ns (server),
        open_utc_ns, close_utc_ns (all int64 ns). Index = bar open time (server)."""
        tf = tf.upper()
        if tf not in self._bars:
            arr = resample_arrays(self.t, self.o, self.h, self.l, self.c, self.spread, self.vol, tf)
            self._bars[tf] = _bars_frame(arr)
        return self._bars[tf]

    def index_at_or_after(self, time_ns) -> int:
        return int(np.searchsorted(self.t, time_ns, side="left"))

    def info(self) -> dict:
        d = {"n_m1": int(len(self.t)), "first_bar": str(self.first_time), "last_bar": str(self.last_time),
             "symbol": self.spec.symbol}
        d.update({k: v for k, v in self.source.items() if k != "quality"})
        return d

    def slice(self, start=None, end=None) -> "MarketData":
        """New MarketData restricted to [start, end) (server time)."""
        m = self.m1
        if start is not None:
            m = m[m.index >= pd.Timestamp(start)]
        if end is not None:
            m = m[m.index < pd.Timestamp(end)]
        return MarketData(m, self.spec, self.source)


def last_closed_index(close_times_ns: np.ndarray, t_ns) -> np.ndarray | int:
    """Index of the last bar whose close time is <= t (-1 if none). Past-only lookup."""
    return np.searchsorted(close_times_ns, t_ns, side="right") - 1


def parse_time_arg(t, default=None):
    """None/str/Timestamp -> int ns (naive server time)."""
    if t is None:
        return default
    return to_ns(t)


__all__ = [
    "TF_MINUTES", "SymbolSpec", "load_spec", "load_mt5_csv", "parse_server_times", "resample_bars",
    "resample_arrays", "MarketData", "file_sha256", "last_closed_index", "tf_ns", "bar_report",
    "NS_PER_DAY",
]
