"""Time conversion, loaders and resampling."""
import json

import numpy as np
import pandas as pd
import pytest

from conftest import make_md
from kq.data import MarketData, SymbolSpec, load_mt5_csv, load_spec, resample_bars
from kq.synth import generate_m1, write_mt5_csv
from kq.timeutil import server_to_utc, server_utc_offset_hours, utc_to_server


def test_server_to_utc_follows_new_york_dst():
    # US winter: server = UTC+2
    assert server_to_utc(pd.Timestamp("2024-01-15 10:00")) == pd.Timestamp("2024-01-15 08:00")
    # US summer: server = UTC+3
    assert server_to_utc(pd.Timestamp("2024-07-15 10:00")) == pd.Timestamp("2024-07-15 07:00")
    # 2024-03-12: US already on DST (since 03-10), Europe not yet -> still UTC+3
    assert server_to_utc(pd.Timestamp("2024-03-12 10:00")) == pd.Timestamp("2024-03-12 07:00")
    # 2024-11-01: Europe back to winter time, US still on DST until 11-03 -> UTC+3
    assert server_to_utc(pd.Timestamp("2024-11-01 10:00")) == pd.Timestamp("2024-11-01 07:00")
    # the daily break 17:00 New York is 00:00 server
    ny = pd.Timestamp("2024-07-15 17:00", tz="America/New_York")
    assert utc_to_server(ny) == pd.Timestamp("2024-07-16 00:00")
    assert server_utc_offset_hours(pd.Timestamp("2024-01-15 12:00")) == 2.0


def test_server_to_utc_accepts_arrays_and_roundtrips():
    idx = pd.date_range("2024-03-01", "2024-04-01", freq="7h")
    utc = server_to_utc(idx)
    assert isinstance(utc, pd.DatetimeIndex) and len(utc) == len(idx)
    np.testing.assert_array_equal(utc_to_server(utc).asi8, idx.as_unit("ns").asi8)
    ns = server_to_utc(idx.as_unit("ns").asi8)
    np.testing.assert_array_equal(ns, utc.as_unit("ns").asi8)
    s = server_to_utc(pd.Series(idx))
    assert isinstance(s, pd.Series)


def _write(path, lines, encoding="utf-8"):
    path.write_text("\n".join(lines) + "\n", encoding=encoding)
    return path


@pytest.mark.parametrize("fmt,enc", [("%Y.%m.%d %H:%M", "utf-8"), ("%Y-%m-%d %H:%M", "utf-8"),
                                     ("%Y-%m-%d %H:%M:%S", "utf-8"), ("%Y.%m.%d %H:%M", "utf-16")])
def test_load_mt5_csv_formats(tmp_path, fmt, enc):
    t = pd.date_range("2024-01-09 10:00", periods=4, freq="1min")
    lines = ["time,open,high,low,close,tick_volume,spread,real_volume"]
    for i, x in enumerate(t):
        lines.append(f"{x.strftime(fmt)},{2000 + i:.2f},{2001 + i:.2f},{1999 + i:.2f},{2000.5 + i:.2f},10,{20 + i},0")
    df = load_mt5_csv(_write(tmp_path / "a.csv", lines, enc))
    assert list(df.index) == list(t)
    assert df.index.dtype == "datetime64[ns]"
    assert df["spread"].tolist() == [20, 21, 22, 23]
    assert df["close"].iloc[-1] == pytest.approx(2003.5)


def test_load_mt5_csv_cleans_duplicates_order_and_bad_ohlc(tmp_path):
    lines = ["time,open,high,low,close,tick_volume,spread,real_volume",
             "2024.01.09 10:02,2002,2003,2001,2002.5,1,20,0",
             "2024.01.09 10:00,2000,2001,1999,2000.5,1,20,0",
             "2024.01.09 10:01,2001,2000,2002,2001.5,1,20,0",      # high < low: repaired
             "2024.01.09 10:00,2000,2001.5,1999,2000.7,1,25,0",    # duplicate: keep last
             "2024.01.09 10:03,0,0,0,0,1,20,0"]                    # bad price: dropped
    df, rep = load_mt5_csv(_write(tmp_path / "b.csv", lines), return_report=True)
    assert len(df) == 3 and df.index.is_monotonic_increasing
    assert df.loc["2024-01-09 10:00", "close"] == pytest.approx(2000.7)
    r = df.loc["2024-01-09 10:01"]
    assert r.high == pytest.approx(2002) and r.low == pytest.approx(2000)
    assert rep["duplicates_dropped"] == 1 and rep["rows_bad_ohlc"] == 1 and rep["rows_bad_price_dropped"] == 1


def test_load_mt5_export_bars_format(tmp_path):
    lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>",
             "2024.01.09\t10:00:00\t2000\t2001\t1999\t2000.5\t5\t0\t18",
             "2024.01.09\t10:01:00\t2000.5\t2001\t2000\t2000.8\t5\t0\t19"]
    df = load_mt5_csv(_write(tmp_path / "c.csv", lines))
    assert df.index[1] == pd.Timestamp("2024-01-09 10:01") and df["spread"].tolist() == [18, 19]


def test_synth_roundtrip_through_csv(tmp_path):
    df = generate_m1("2024-01-08", "2024-01-10", seed=1)
    p = tmp_path / "KQ_XAUUSD_M1.csv"
    write_mt5_csv(df, p)
    assert p.read_text().splitlines()[1].startswith("2024.01.08 01:00,")
    back = load_mt5_csv(p)
    pd.testing.assert_index_equal(back.index, df.index)
    np.testing.assert_allclose(back["close"].to_numpy(), df["close"].to_numpy())


def test_load_spec(tmp_path):
    p = tmp_path / "KQ_XAUUSD_spec.json"
    p.write_text(json.dumps({"symbol": "XAUUSDc", "digits": "2", "point": 0.01, "contract_size": 100,
                             "volume_min": 0.01, "swap_long": -55.5, "swap_mode": 1, "account_currency": "USC",
                             "margin_initial": 0}))
    s = load_spec(p)
    assert s.symbol == "XAUUSDc" and s.digits == 2 and s.swap_mode == "points" and s.swap_long == -55.5
    assert s.extra == {"margin_initial": 0} and s.default_units_per_usd() == 100.0
    with pytest.warns(UserWarning):
        d = load_spec(tmp_path / "missing.json")
    assert d == SymbolSpec()


def test_resample_labels_and_ohlc():
    t = pd.date_range("2024-01-09 01:00", "2024-01-10 23:59", freq="1min")
    rows = [(x, 1000 + i * 0.01, 1000 + i * 0.01 + 0.5, 1000 + i * 0.01 - 0.5, 1000 + i * 0.01, 10 + (i % 7))
            for i, x in enumerate(t)]
    md = make_md(rows)
    h4 = md.bars("H4")
    assert set(h4.index.hour) == {0, 4, 8, 12, 16, 20}
    assert h4.index[0] == pd.Timestamp("2024-01-09 00:00")          # labelled by open time
    assert h4.n_m1.iloc[0] == 180                                      # 01:00-03:59
    d1 = md.bars("D1")
    assert list(d1.index) == [pd.Timestamp("2024-01-09"), pd.Timestamp("2024-01-10")]
    assert (d1.close_time_ns.to_numpy() - d1.index.asi8 == 86_400 * 10**9).all()
    b = h4.iloc[1]                                                     # 04:00-07:59
    m1 = md.m1.loc["2024-01-09 04:00":"2024-01-09 07:59"]
    assert b.open == m1.open.iloc[0] and b.close == m1.close.iloc[-1]
    assert b.high == m1.high.max() and b.low == m1.low.min() and b.spread == m1.spread.iloc[-1]
    pd.testing.assert_frame_equal(resample_bars(md.m1, "H4")[["open", "high", "low", "close"]],
                                  h4[["open", "high", "low", "close"]])
    m5 = md.bars("M5")
    assert (m5.index.minute % 5 == 0).all() and (m5.n_m1 == 5).all()


def test_marketdata_rejects_unsorted():
    df = pd.DataFrame({"open": [1, 1], "high": [1, 1], "low": [1, 1], "close": [1, 1], "spread": [1, 1]},
                      index=pd.DatetimeIndex(["2024-01-02 10:01", "2024-01-02 10:00"]))
    with pytest.raises(ValueError):
        MarketData(df)
