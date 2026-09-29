"""Append-only experiment registry (JSONL).

Every run appends ONE line to ``research/registry/experiments.jsonl``. The file is opened
with O_APPEND (the OS guarantees writes go to the end; existing bytes are never rewritten),
under an exclusive lock, and each line stores ``prev_line_sha256`` — the SHA-256 of the
previous line — so any edit or deletion of an earlier line is detected by
:func:`verify_registry`.

The chain alone cannot see the LAST lines being edited or removed, so the head is anchored
outside the file twice:
* ``<registry>.head`` gets one line per append with the line count and the SHA-256 of the
  new last line (also append-only);
* when the registry is tracked by git, the committed version must be a prefix of the
  current file (commit the registry after every real-data run).
Duplicate ``experiment_id`` values are rejected.
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
    """Commit of the code and whether the research tree (``research/``, code and presets that
    define the experiment; the registry itself excluded) has uncommitted changes."""
    cwd = str(Path(path).resolve() if path else Path(__file__).resolve().parent.parent)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True,
                                timeout=5).stdout.strip() or None
        dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", ":(exclude)registry"], cwd=cwd,
                               capture_output=True, text=True, timeout=5).stdout.strip() != ""
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


def head_path(path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".head")


def _lines(path: Path) -> list[bytes]:
    if not path.exists():
        return []
    with open(path, "rb") as f:
        return [x for x in f.read().split(b"\n") if x.strip()]


def append_experiment(record: dict, path=None) -> dict:
    """Append one record; returns the record as written (with timestamp and chain hash).
    Raises ValueError if the ``experiment_id`` already exists."""
    path = Path(path or DEFAULT_REGISTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        existing = _lines(path)
        rec = dict(record)
        rec.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        if not rec.get("experiment_id"):
            rec["experiment_id"] = uuid.uuid4().hex[:12]
        ids = {json.loads(x).get("experiment_id") for x in existing}
        if rec["experiment_id"] in ids:
            raise ValueError(f"experiment_id {rec['experiment_id']!r} already in the registry")
        prev = existing[-1] if existing else None
        rec["prev_line_sha256"] = hashlib.sha256(prev).hexdigest() if prev is not None else None
        line = json.dumps(sanitize(rec), sort_keys=True, ensure_ascii=False, allow_nan=False)
        if "\n" in line:
            raise ValueError("record serialised with a newline")
        raw = line.encode("utf-8")
        os.write(fd, raw + b"\n")
        os.fsync(fd)
        head = {"n": len(existing) + 1, "last_line_sha256": hashlib.sha256(raw).hexdigest(),
                "experiment_id": rec["experiment_id"], "timestamp_utc": rec["timestamp_utc"]}
        hfd = os.open(str(head_path(path)), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(hfd, (json.dumps(head, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(hfd)
        finally:
            os.close(hfd)
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return json.loads(line)


def _git_prefix_ok(path: Path) -> bool | None:
    """True if the version committed at HEAD is a prefix of the current file, False if not,
    None if the file is not tracked (or git is unavailable)."""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(path.parent), capture_output=True,
                             text=True, timeout=5)
        if top.returncode != 0:
            return None
        rel = path.resolve().relative_to(Path(top.stdout.strip()).resolve()).as_posix()
        shown = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(path.parent), capture_output=True, timeout=10)
        if shown.returncode != 0:
            return None
        current = path.read_bytes() if path.exists() else b""
        return current.startswith(shown.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def read_registry(path=None) -> list[dict]:
    path = Path(path or DEFAULT_REGISTRY)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def verify_registry(path=None, check_git: bool = True) -> dict:
    """Check the hash chain, the head file and (if tracked) that the committed version is a
    prefix of the current file. Returns {'ok', 'n', 'first_bad_line', 'problems'}."""
    path = Path(path or DEFAULT_REGISTRY)
    lines = _lines(path)
    problems, first_bad = [], None
    prev = None
    ids = set()
    for i, raw in enumerate(lines):
        rec = json.loads(raw)
        want = hashlib.sha256(prev).hexdigest() if prev is not None else None
        if rec.get("prev_line_sha256") != want and first_bad is None:
            first_bad = i
            problems.append(f"hash chain broken at line {i}")
        if rec.get("experiment_id") in ids:
            problems.append(f"duplicate experiment_id {rec.get('experiment_id')!r}")
        ids.add(rec.get("experiment_id"))
        prev = raw
    hp = head_path(path)
    heads = [json.loads(x) for x in _lines(hp)]
    if lines and not heads:
        problems.append("head file missing: the last records cannot be verified")
    for h in heads:
        n = int(h.get("n", 0))
        if n > len(lines):
            problems.append(f"head says {n} records but the registry has {len(lines)} (records removed)")
            break
        if n >= 1 and hashlib.sha256(lines[n - 1]).hexdigest() != h.get("last_line_sha256"):
            problems.append(f"record {n - 1} differs from the one recorded in the head file")
            break
    if heads and int(heads[-1].get("n", 0)) != len(lines):
        problems.append("registry and head file disagree on the number of records")
    if check_git:
        for f in (path, hp):
            if _git_prefix_ok(f) is False:
                problems.append(f"{f.name}: the committed version is not a prefix of the current file")
    return {"ok": not problems, "n": len(lines), "first_bad_line": first_bad, "problems": problems}


CONTROL_STRATEGIES = {"RANDOM_ENTRY", "BUY_HOLD", "BUY_HOLD_VOLSCALED", "SCRIPTED"}


def config_key(strategy: str, params: dict | None) -> str:
    """Stable identifier of a strategy configuration (order of keys irrelevant)."""
    blob = json.dumps({"strategy": str(strategy).upper(), "params": sanitize(params or {})}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def distinct_config_keys(records: list[dict]) -> set[str]:
    """Candidate configurations tried so far according to the registry (controls, benchmarks
    and holdout locks excluded). Protocol records list their grid in ``config_keys``."""
    keys = set()
    for rec in records:
        if rec.get("record_type") == "holdout_lock":
            continue
        if rec.get("config_keys"):
            keys.update(rec["config_keys"])
            continue
        st = rec.get("strategy")
        if isinstance(st, dict) and st.get("name") and str(st["name"]).upper() not in CONTROL_STRATEGIES:
            keys.add(config_key(st["name"], st.get("params")))
    return keys


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
