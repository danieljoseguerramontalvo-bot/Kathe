"""Cargador de Dukascopy: decodificación .bi5, URL, divisor, conversión a hora del servidor y CSV compatible."""
import datetime as dt
import lzma
import struct

import numpy as np
import pandas as pd
import pytest

from kq import dukascopy as dk
from kq.data import load_mt5_csv


def _bi5(records):
    raw = b"".join(struct.pack(">5if", *r) for r in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def test_day_url_month_is_zero_based():
    url = dk.day_url("xauusd", dt.date(2024, 1, 5), "bid")
    assert url.endswith("/XAUUSD/2024/00/05/BID_candles_min_1.bi5")
    assert "/2024/11/31/" in dk.day_url("XAUUSD", dt.date(2024, 12, 31), "ASK")
    with pytest.raises(ValueError):
        dk.day_url("XAUUSD", dt.date(2024, 1, 5), "MID")


def test_parse_candles_roundtrip():
    recs = [(0, 2000123, 2000456, 1999900, 2000500, 1.5), (60, 2000456, 2000100, 2000000, 2000600, 0.25)]
    out = dk.parse_candles(_bi5(recs))
    assert out.shape == (2, 6)
    np.testing.assert_allclose(out, np.array(recs, dtype=float), rtol=0, atol=1e-6)
    assert dk.parse_candles(b"").shape == (0, 6)


def test_parse_candles_rejects_truncated_payload():
    raw = struct.pack(">5if", 0, 1, 1, 1, 1, 1.0)[:-3]
    with pytest.raises(ValueError):
        dk.parse_candles(lzma.compress(raw, format=lzma.FORMAT_ALONE))


def test_detect_divisor():
    assert dk.detect_divisor(np.array([1_850_000.0, 1_900_000.0])) == 1000.0  # 1850-1900 USD
    assert dk.detect_divisor(np.array([185_000.0])) == 100.0
    with pytest.raises(ValueError):
        dk.detect_divisor(np.array([5.0]))


def test_candles_to_frame_server_time_spread_and_flat_minutes():
    day = dt.date(2024, 1, 10)  # invierno EE. UU.: servidor = UTC + 2
    bid = np.array([
        [0, 2000_000, 2000_500, 1999_000, 2001_000, 3.0],
        [60, 2000_500, 2000_500, 2000_500, 2000_500, 0.0],  # minuto sin cotizaciones: se descarta
        [120, 2000_500, 2001_000, 2000_400, 2001_200, 2.0],
    ], dtype=float)
    ask = bid.copy()
    ask[:, 1:5] += 250  # 0.25 USD = 25 puntos de 0.01
    ask = np.delete(ask, 2, axis=0)  # falta el ASK del minuto 2
    f = dk.candles_to_frame(day, bid, ask, divisor=1000.0, point=0.01)
    assert list(f["time"]) == [pd.Timestamp("2024-01-10 02:00"), pd.Timestamp("2024-01-10 02:02")]
    assert f["open"].iloc[0] == pytest.approx(2000.0)
    assert f["high"].iloc[0] == pytest.approx(2001.0)
    assert f["spread"].tolist() == [25, -1]  # -1 = sin ASK, lo rellena download()


def test_candles_to_frame_summer_offset():
    day = dt.date(2024, 7, 10)  # verano EE. UU.: servidor = UTC + 3
    bid = np.array([[3600, 2400_000, 2400_000, 2400_000, 2400_000, 1.0]], dtype=float)
    f = dk.candles_to_frame(day, bid, bid.copy(), divisor=1000.0, point=0.01)
    assert f["time"].iloc[0] == pd.Timestamp("2024-07-10 04:00")
    assert f["spread"].iloc[0] == 0


def test_download_writes_mt5_compatible_csv(tmp_path, monkeypatch):
    def rec(s, p):
        return (s, p, p + 100, p - 100, p + 200, 1.0)

    payloads = {
        ("BID", dt.date(2024, 1, 8)): _bi5([rec(0, 2000_000), rec(60, 2000_100)]),
        ("ASK", dt.date(2024, 1, 8)): _bi5([rec(0, 2000_300)]),  # minuto 1 sin ASK -> mediana del día
        ("BID", dt.date(2024, 1, 9)): _bi5([rec(0, 2010_000)]),
        ("ASK", dt.date(2024, 1, 9)): _bi5([rec(0, 2010_200)]),
    }

    def fake_fetch(url, cache_path, retries=4, timeout=30.0):
        for (side, day), data in payloads.items():
            if url == dk.day_url("XAUUSD", day, side):
                return data
        return b""

    monkeypatch.setattr(dk, "_fetch", fake_fetch)
    out = tmp_path / "KQ_XAUUSD_M1.csv"
    summary = dk.download("XAUUSD", dt.date(2024, 1, 8), dt.date(2024, 1, 9), out, tmp_path / "cache",
                          workers=2, progress=False)
    assert summary["rows"] == 3
    assert summary["price_divisor"] == 1000.0
    assert summary["missing_spread_filled"] == 1
    assert out.read_text().splitlines()[0] == "time,open,high,low,close,tick_volume,spread,real_volume"

    df = load_mt5_csv(out)
    assert len(df) == 3
    assert df.index[0] == pd.Timestamp("2024-01-08 02:00")
    assert df["open"].iloc[2] == pytest.approx(2010.0)
    assert df["spread"].tolist() == [30, 30, 20]
