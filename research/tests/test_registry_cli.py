"""Append-only registry and the command line."""
import json

import pandas as pd
import pytest

from kq import run as cli
from kq.registry import append_experiment, read_registry, verify_registry
from kq.synth import default_spec_dict, generate_m1, write_mt5_csv


def test_registry_is_append_only_and_hash_chained(tmp_path):
    p = tmp_path / "experiments.jsonl"
    a = append_experiment({"experiment_id": "a", "metrics": {"x": float("nan"), "y": 1.5}}, p)
    first = p.read_bytes()
    b = append_experiment({"experiment_id": "b", "metrics": {"x": 2}}, p)
    data = p.read_bytes()
    assert data.startswith(first)                         # earlier bytes untouched
    assert len(data.splitlines()) == 2
    recs = read_registry(p)
    assert [r["experiment_id"] for r in recs] == ["a", "b"]
    assert recs[0]["metrics"]["x"] is None                # NaN -> null (strict JSON)
    assert a["prev_line_sha256"] is None and b["prev_line_sha256"] is not None
    assert "timestamp_utc" in recs[0]
    assert verify_registry(p)["ok"]
    # editing an earlier line is detected
    lines = data.decode().splitlines()
    lines[0] = lines[0].replace('"y": 1.5', '"y": 9.9')
    p.write_text("\n".join(lines) + "\n")
    v = verify_registry(p)
    assert not v["ok"] and v["first_bad_line"] == 1


def test_registry_appends_to_existing_content(tmp_path):
    p = tmp_path / "r.jsonl"
    append_experiment({"experiment_id": "old"}, p)
    before = p.read_bytes()
    for k in range(3):
        append_experiment({"experiment_id": f"n{k}"}, p)
        assert p.read_bytes().startswith(before)
    assert verify_registry(p) == {"ok": True, "n": 4, "first_bad_line": None}


@pytest.fixture(scope="module")
def small_csv(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    df = generate_m1("2023-01-02", "2023-07-01", seed=3, trend_regime_annual=0.3)
    csv = d / "KQ_XAUUSD_M1.csv"
    spec = d / "KQ_XAUUSD_spec.json"
    write_mt5_csv(df, csv)
    spec.write_text(json.dumps(default_spec_dict()))
    return csv, spec


def _strict_json(path):
    def bad(x):
        raise ValueError(f"non-standard JSON constant {x}")
    with open(path) as f:
        return json.load(f, parse_constant=bad)


def test_cli_end_to_end_and_registry(tmp_path, small_csv, capsys):
    csv, spec = small_csv
    reg = tmp_path / "reg.jsonl"
    out = tmp_path / "run1"
    args = ["--data", str(csv), "--spec", str(spec), "--strategy", "TREND_DONCHIAN", "--params", '{"n": 20}',
            "--start", "2023-02-01", "--end", "2023-06-30", "--out", str(out), "--registry", str(reg),
            "--hypothesis-id", "H_TSMOM", "--split", "dev", "--commission", "7", "--slippage-points", "5",
            "--swap", "--n-boot", "200", "--n-mc", "200"]
    assert cli.main(args) == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    for f in ("trades.csv", "equity.csv", "metrics.json", "skipped.csv", "daily_returns.csv"):
        assert (out / f).exists(), f
    m = _strict_json(out / "metrics.json")
    assert m["metrics"]["n_trades"] == summary["n_trades"] > 0
    assert m["run"]["config"]["end"] == "2023-07-01 00:00:00"          # --end is inclusive
    trades = pd.read_csv(out / "trades.csv", parse_dates=["entry_time", "exit_time"])
    assert trades.entry_time.min() >= pd.Timestamp("2023-02-01")
    assert trades.exit_time.max() < pd.Timestamp("2023-07-01")
    recs = read_registry(reg)
    assert len(recs) == 1
    r = recs[0]
    assert r["hypothesis_id"] == "H_TSMOM" and r["split"] == "dev"
    assert r["strategy"]["params"]["n"] == 20 and r["strategy"]["params"]["k_trail"] == 3.0
    assert len(r["data"]["sha256"]) == 64 and r["data"]["range_first_bar"].startswith("2023-02-01")
    assert r["costs"]["commission_per_lot_rt"] == 7 and r["costs"]["apply_swap"] is True
    assert "git_commit" in r and r["metrics"]["n_trades"] == summary["n_trades"]
    first = reg.read_bytes()
    args2 = ["--data", str(csv), "--spec", str(spec), "--strategy", "REF_T0", "--start", "2023-02-01",
             "--end", "2023-06-30", "--out", str(tmp_path / "run2"), "--registry", str(reg), "--n-boot", "100",
             "--n-mc", "100", "--no-benchmarks"]
    assert cli.main(args2) == 0
    assert reg.read_bytes().startswith(first) and len(read_registry(reg)) == 2
    assert verify_registry(reg)["ok"]


def test_cli_benchmark_and_random_entry(tmp_path, small_csv, capsys):
    csv, spec = small_csv
    reg = tmp_path / "reg.jsonl"
    base = ["--data", str(csv), "--spec", str(spec), "--start", "2023-02-01", "--end", "2023-06-30",
            "--registry", str(reg), "--n-boot", "100", "--n-mc", "100"]
    assert cli.main(base + ["--strategy", "BUY_HOLD_VOLSCALED", "--out", str(tmp_path / "bh")]) == 0
    m = _strict_json(tmp_path / "bh" / "metrics.json")["metrics"]
    assert m["name"] == "BUY_HOLD_VOLSCALED" and m["n_rebalances"] > 0
    assert cli.main(base + ["--strategy", "RANDOM_ENTRY", "--params",
                            '{"target": "TREND_DONCHIAN", "seed": 4}', "--out", str(tmp_path / "rnd")]) == 0
    m = _strict_json(tmp_path / "rnd" / "metrics.json")
    assert 0 < m["run"]["strategy"]["params"]["p_entry"] < 1
    assert len(read_registry(reg)) == 2
