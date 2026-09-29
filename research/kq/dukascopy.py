"""Descarga de velas M1 BID/ASK de Dukascopy y conversión al formato de exportación de MT5.

Solo funciona si la política de red del entorno permite ``datafeed.dukascopy.com``.

Formato del feed público (archivos diarios, hora UTC):

    https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM0}/{DD}/{BID|ASK}_candles_min_1.bi5

- ``MM0`` es el mes empezando en 0 (enero = "00").
- El archivo está comprimido con LZMA (formato "alone").
- Cada registro ocupa 24 bytes big-endian: ``segundos_desde_00:00_UTC, open, close, low, high`` como enteros
  (precio x divisor) y ``volumen`` como float32.
- Los días sin mercado devuelven un archivo vacío o 404.

La salida es un CSV con el mismo formato que ``Scripts/KQ_ExportarHistorial.mq5``:

- ``time`` en hora del *servidor* (Nueva York + 7 h, como HF Markets) y precios BID;
- ``spread`` en puntos del bróker (``point`` = 0.01 por defecto) = ask_open - bid_open.

Así ``kq.data.load_mt5_csv`` lo carga igual que una exportación de MT5.

Límites (anotados también en el README):

- Los precios y spreads son los de Dukascopy, no los de HF Markets. El spread de Dukascopy suele ser
  menor que el de un CFD minorista, así que el modelo de costes debe añadir el diferencial observado
  con el script de auditoría o, como mínimo, las pruebas de estrés de +10, +20 y +40 puntos.
- El divisor de precio se detecta y se valida por rango de precios; queda anotado en el resumen.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import lzma
import os
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from .timeutil import utc_to_server

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
RECORD = struct.Struct(">5if")  # time_s, open, close, low, high, volume
RECORD_DTYPE = np.dtype([("s", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])
CANDIDATE_DIVISORS = (1000.0, 100.0, 100000.0, 10.0)


def day_url(symbol: str, day: dt.date, side: str) -> str:
    """URL del archivo diario de velas M1 (``side`` = 'BID' o 'ASK'); el mes empieza en 0."""
    side = side.upper()
    if side not in ("BID", "ASK"):
        raise ValueError("side debe ser BID o ASK")
    return f"{BASE_URL}/{symbol.upper()}/{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/{side}_candles_min_1.bi5"


def parse_candles(raw: bytes) -> np.ndarray:
    """Descomprime y decodifica un archivo .bi5 de velas. Devuelve un array (n, 6) float64
    con columnas time_s, open, close, low, high, volume (precios aún sin dividir)."""
    if not raw:
        return np.empty((0, 6))
    data = lzma.decompress(raw, format=lzma.FORMAT_AUTO)
    n = len(data) // RECORD.size
    if n * RECORD.size != len(data):
        raise ValueError(f"tamaño inesperado: {len(data)} bytes no es múltiplo de {RECORD.size}")
    rec = np.frombuffer(data, dtype=RECORD_DTYPE, count=n)
    return np.column_stack([rec[f].astype(np.float64) for f in RECORD_DTYPE.names])


def detect_divisor(raw_prices: np.ndarray, expected_range=(200.0, 20000.0)) -> float:
    """Elige el divisor que sitúa la mediana de los precios dentro del rango esperado para el oro."""
    med = float(np.median(raw_prices)) if len(raw_prices) else 0.0
    for d in CANDIDATE_DIVISORS:
        if expected_range[0] <= med / d <= expected_range[1]:
            return d
    raise ValueError(f"no se pudo determinar el divisor de precio (mediana bruta {med})")


def _fetch(url: str, cache_path: Path, retries: int = 4, timeout: float = 30.0) -> bytes:
    if cache_path.exists():
        return cache_path.read_bytes()
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kq-research/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".part")
            tmp.write_bytes(data)
            os.replace(tmp, cache_path)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(b"")
                return b""
            if attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    return b""


def candles_to_frame(day: dt.date, bid: np.ndarray, ask: np.ndarray, divisor: float, point: float) -> pd.DataFrame:
    """Une BID y ASK de un día en velas M1 BID con spread en puntos, en hora del servidor."""
    if len(bid) == 0:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
    day0 = pd.Timestamp(day)
    b = pd.DataFrame(bid, columns=["s", "o", "c", "l", "h", "v"])
    b["utc"] = day0 + pd.to_timedelta(b["s"].astype("int64"), unit="s")
    b = b[b["v"] > 0]  # minutos sin cotizaciones (Dukascopy repite el precio con volumen 0)
    if len(ask):
        a = pd.DataFrame(ask, columns=["s", "o", "c", "l", "h", "v"])
        a["utc"] = day0 + pd.to_timedelta(a["s"].astype("int64"), unit="s")
        b = b.merge(a[["utc", "o"]].rename(columns={"o": "ask_o"}), on="utc", how="left")
    else:
        b["ask_o"] = np.nan
    spread_price = (b["ask_o"] - b["o"]) / divisor
    spread_pts = np.round(spread_price / point)
    out = pd.DataFrame({
        "time": utc_to_server(pd.DatetimeIndex(b["utc"])),
        "open": b["o"] / divisor,
        "high": b["h"] / divisor,
        "low": b["l"] / divisor,
        "close": b["c"] / divisor,
        "tick_volume": np.maximum(1, np.round(b["v"])).astype("int64"),
        "spread": spread_pts.fillna(-1).astype("int64"),
        "real_volume": 0,
    })
    return out


def download(symbol: str, start: dt.date, end: dt.date, out_csv: Path, cache_dir: Path,
             point: float = 0.01, workers: int = 8, divisor: float | None = None, progress: bool = True) -> dict:
    """Descarga [start, end] (fechas UTC) y escribe un CSV en el formato de MT5. Devuelve un resumen.

    El spread que falta (minuto sin ASK) se rellena con la mediana del día y se cuenta en el resumen.
    """
    days = [start + dt.timedelta(d) for d in range((end - start).days + 1)]
    days = [d for d in days if d.weekday() != 5]  # sábado: sin mercado
    jobs = []
    for d in days:
        for side in ("BID", "ASK"):
            url = day_url(symbol, d, side)
            cache = cache_dir / symbol.upper() / f"{d:%Y}" / f"{d:%Y%m%d}_{side}.bi5"
            jobs.append((d, side, url, cache))
    raw: dict[tuple, bytes] = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch, url, cache): (d, side) for d, side, url, cache in jobs}
        for k, f in enumerate(cf.as_completed(futs), 1):
            raw[futs[f]] = f.result()
            if progress and k % 500 == 0:
                print(f"  {k}/{len(jobs)} archivos")

    parsed = {key: parse_candles(v) for key, v in raw.items()}
    if divisor is None:
        sample = np.concatenate([p[:, 1] for p in parsed.values() if len(p)][:50] or [np.array([0.0])])
        divisor = detect_divisor(sample)
    frames, missing_spread, days_with_data = [], 0, 0
    for d in days:
        f = candles_to_frame(d, parsed[(d, "BID")], parsed[(d, "ASK")], divisor, point)
        if len(f) == 0:
            continue
        days_with_data += 1
        bad = f["spread"] < 0
        if bad.any():
            missing_spread += int(bad.sum())
            med = int(f.loc[~bad, "spread"].median()) if (~bad).any() else 0
            f.loc[bad, "spread"] = med
        frames.append(f)
    df = pd.concat(frames, ignore_index=True).sort_values("time").drop_duplicates("time")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.assign(time=df["time"].dt.strftime("%Y.%m.%d %H:%M")).to_csv(out_csv, index=False, float_format="%.3f")
    return {
        "symbol": symbol.upper(), "start": str(start), "end": str(end), "rows": int(len(df)),
        "days_with_data": days_with_data, "price_divisor": divisor, "point": point,
        "missing_spread_filled": missing_spread, "median_spread_points": float(df["spread"].median()),
        "out_csv": str(out_csv), "source": "dukascopy datafeed (BID/ASK M1 candles), UTC -> server NY+7",
    }


def main(argv=None):
    import argparse
    import json
    p = argparse.ArgumentParser(description="Descarga velas M1 de Dukascopy al formato de exportación de MT5")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--start", required=True, help="YYYY-MM-DD (UTC)")
    p.add_argument("--end", required=True, help="YYYY-MM-DD (UTC)")
    p.add_argument("--out", required=True, help="CSV de salida")
    p.add_argument("--cache", default="data/raw/dukascopy")
    p.add_argument("--point", type=float, default=0.01)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args(argv)
    summary = download(a.symbol, dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end),
                       Path(a.out), Path(a.cache), point=a.point, workers=a.workers)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
