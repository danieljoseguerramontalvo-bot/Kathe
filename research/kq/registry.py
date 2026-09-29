"""Append-only experiment registry (JSONL).

Every run appends ONE line to ``research/registry/experiments.jsonl``. The file is opened
with O_APPEND (the OS guarantees writes go to the end; existing bytes are never rewritten),
under an exclusive lock, and each line stores ``prev_line_sha256`` — the SHA-256 of the
previous line — so any edit or deletion of an earlier line is detected by
:func:`verify_registry`.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "registry" / "experiments.jsonl"

try:  # POSIX advisory lock; on Windows appends are still O_APPEND
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def sanitize(obj):
    """Make an object strictly JSON-serialisable (NaN/inf -> None, numpy -> python)."""
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [sanitize(v) for v in obj.tolist()]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (pd.Timestamp, datetime)):
        return str(obj)
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    return repr(obj)


def git_info(path=None) -> dict:
    cwd = str(Path(path or __file__).resolve().parent)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True,
                                timeout=5).stdout.strip() or None
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=cwd, capture_output=True,
                               text=True, timeout=5).stdout.strip() != ""
        return {"git_commit": commit, "git_dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": None, "git_dirty": None}


def _last_line(path: Path) -> bytes | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = b""
        pos = size
        while pos > 0:
            step = min(4096, pos)
            pos -= step
            f.seek(pos)
            block = f.read(step) + block
            lines = block.rstrip(b"\n").split(b"\n")
            if len(lines) > 1 or pos == 0:
                return lines[-1]
    return None


def append_experiment(record: dict, path=None) -> dict:
    """Append one record; returns the record as written (with timestamp and chain hash)."""
    path = Path(path or DEFAULT_REGISTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        prev = _last_line(path)
        rec = dict(record)
        rec.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        rec.setdefault("experiment_id", uuid.uuid4().hex[:12])
        rec["prev_line_sha256"] = hashlib.sha256(prev).hexdigest() if prev is not None else None
        line = json.dumps(sanitize(rec), sort_keys=True, ensure_ascii=False, allow_nan=False)
        if "\n" in line:
            raise ValueError("record serialised with a newline")
        os.write(fd, (line + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return json.loads(line)


def read_registry(path=None) -> list[dict]:
    path = Path(path or DEFAULT_REGISTRY)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def verify_registry(path=None) -> dict:
    """Check the hash chain; returns {'ok': bool, 'n': lines, 'first_bad_line': int|None}."""
    path = Path(path or DEFAULT_REGISTRY)
    if not path.exists():
        return {"ok": True, "n": 0, "first_bad_line": None}
    with open(path, "rb") as f:
        lines = [x for x in f.read().split(b"\n") if x.strip()]
    prev = None
    for i, raw in enumerate(lines):
        rec = json.loads(raw)
        want = hashlib.sha256(prev).hexdigest() if prev is not None else None
        if rec.get("prev_line_sha256") != want:
            return {"ok": False, "n": len(lines), "first_bad_line": i}
        prev = raw
    return {"ok": True, "n": len(lines), "first_bad_line": None}


def build_record(result, metrics: dict, md=None, hypothesis_id: str | None = None, split: str | None = None,
                 experiment_id: str | None = None, extra: dict | None = None) -> dict:
    """Standard registry record for a backtest run."""
    data = dict(result.data_info)
    data.update({"range_first_bar": result.stats.get("range_first_bar"),
                 "range_last_bar": result.stats.get("range_last_bar")})
    rec = {
        "experiment_id": experiment_id or uuid.uuid4().hex[:12],
        "hypothesis_id": hypothesis_id,
        "split": split,
        "strategy": result.strategy,
        "data": data,
        "range": {"start": result.config.get("start"), "end": result.config.get("end")},
        "costs": result.config.get("costs"),
        "config": {k: v for k, v in result.config.items() if k != "costs"},
        "spec": result.spec,
        "engine": {"version": result.stats.get("engine_version"),
                   "equity_marking": result.stats.get("equity_mark_to_market")},
        "metrics": metrics,
    }
    rec.update(git_info())
    if extra:
        rec["extra"] = extra
    return rec
