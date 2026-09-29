"""Server-time <-> UTC conversion.

HF Markets MT5 server time = New York local time + 7 hours, so the server clock follows
US daylight-saving dates: it is UTC+2 in (US) winter and UTC+3 in (US) summer, and the
daily break at 17:00 New York is always 00:00 server time.

All timestamps inside the engine are *naive* server times stored as int64 nanoseconds.
These helpers accept scalars, DatetimeIndex, Series or int64-ns arrays and return the
same kind of object.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

NY_TZ = "America/New_York"
SERVER_MINUS_NY = pd.Timedelta(hours=7)

NS_PER_MIN = 60_000_000_000
NS_PER_HOUR = 60 * NS_PER_MIN
NS_PER_DAY = 24 * NS_PER_HOUR


def _as_index(t):
    """Return (DatetimeIndex[ns], kind) for any supported input."""
    if isinstance(t, pd.DatetimeIndex):
        return t.as_unit("ns"), "index"
    if isinstance(t, pd.Series):
        return pd.DatetimeIndex(t).as_unit("ns"), "series"
    if isinstance(t, (str, pd.Timestamp, np.datetime64, datetime)):
        return pd.DatetimeIndex([pd.Timestamp(t)]).as_unit("ns"), "scalar"
    arr = np.asarray(t)
    if arr.dtype.kind in "iu":
        return pd.DatetimeIndex(arr.astype("int64").view("datetime64[ns]")), "ns"
    return pd.DatetimeIndex(arr).as_unit("ns"), "array"


def _restore(idx: pd.DatetimeIndex, kind: str, original):
    if kind == "scalar":
        return idx[0]
    if kind == "series":
        return pd.Series(idx, index=original.index, name=original.name)
    if kind == "ns":
        return idx.as_unit("ns").asi8.copy()
    return idx


def server_to_utc(t, aware: bool = False):
    """Convert naive server timestamps (NY + 7h) to UTC.

    Ambiguous NY local times (the repeated hour when DST ends, a Sunday morning when gold is
    closed) are resolved as DST; non-existent ones are shifted forward.
    Returns naive UTC unless ``aware=True``.
    """
    idx, kind = _as_index(t)
    if idx.tz is not None:
        raise ValueError("server_to_utc expects naive server timestamps")
    ny_local = idx - SERVER_MINUS_NY
    loc = ny_local.tz_localize(NY_TZ, ambiguous=np.ones(len(idx), dtype=bool),
                               nonexistent="shift_forward")
    utc = loc.tz_convert("UTC")
    if not aware:
        utc = utc.tz_localize(None)
    return _restore(utc.as_unit("ns"), kind, t)


def utc_to_server(t):
    """Convert UTC timestamps (naive = UTC, or tz-aware) to naive server time."""
    idx, kind = _as_index(t)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    ny = idx.tz_convert(NY_TZ).tz_localize(None)
    return _restore((ny + SERVER_MINUS_NY).as_unit("ns"), kind, t)


def server_utc_offset_hours(t):
    """Offset (hours) of server time with respect to UTC: 2 (US winter) or 3 (US summer)."""
    idx, kind = _as_index(t)
    utc = server_to_utc(idx)
    off = (idx.asi8 - utc.asi8) / NS_PER_HOUR
    if kind == "scalar":
        return float(off[0])
    return off


def to_ns(t) -> int:
    """Scalar timestamp-like -> int64 ns (naive)."""
    ts = pd.Timestamp(t)
    if ts.tzinfo is not None:
        raise ValueError("expected a naive timestamp")
    return int(ts.as_unit("ns").value)


def ns_to_ts(ns) -> pd.Timestamp:
    return pd.Timestamp(int(ns), unit="ns")


def weekday_of_ns(ns):
    """Python weekday (Monday=0) of naive int64-ns timestamps (vectorised)."""
    days = np.floor_divide(np.asarray(ns, dtype="int64"), NS_PER_DAY)
    return (days + 3) % 7  # 1970-01-01 was a Thursday
