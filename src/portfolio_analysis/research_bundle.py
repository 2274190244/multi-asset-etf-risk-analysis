"""Offline reproduction from compact, source-labelled normalized inputs.

Calls the existing Phase 2–5 engines. No strategy formulas, parameter choices,
provider credentials or archived output packages are embedded here.
"""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np
import pandas as pd

from .backtest_reporting import run_scenarios
from .index_reporting import load_index_rules, run_index_matrix
from .metrics import simple_returns
from .quality import china_sessions
from .robustness import load_robustness_rules, run_robustness
from .robustness_reporting import build_robustness_reports
from .tracking_reporting import analyze_pair

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_TABLES = {
    2: ("summary", "daily", "weights", "trades"),
    3: ("summary", "daily"),
    4: ("summary", "daily", "components", "rebalances"),
    5: ("sensitivity", "frequency_comparison", "stability_summary"),
}


def load_inputs(folder):
    """Return validated prices, long tracking levels and provenance; never fill gaps.

    Input is the normalized sample directory, not a Phase output or raw archive.
    Hashes cover every numerical input and its provenance. Validation preserves
    the original Tracking calendars/missing dates for the existing aligner.
    """
    folder = Path(folder)
    hashes = json.loads((folder / "sha256.json").read_text(encoding="utf-8"))
    if set(hashes) != {"market_prices.csv", "tracking_levels.csv", "provenance.json"}:
        raise ValueError("Unexpected input manifest files")
    for name, digest in hashes.items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Input hash mismatch: " + name)
    meta = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    if meta["schema_version"] != 1 or meta["raw_evidence_included"] is not False:
        raise ValueError("Unsupported normalized input contract")
    prices = pd.read_csv(folder / "market_prices.csv", index_col="date", parse_dates=["date"], float_precision="round_trip")
    expected = china_sessions(meta["start"], meta["end"]).rename("date")
    if not prices.index.equals(expected) or not prices.index.is_unique:
        raise ValueError("Market price calendar mismatch; no silent drop/fill")
    if set(prices) != {"159915.SZ", "510300.SS", "510500.SS", "511010.SS", "518880.SS"}:
        raise ValueError("Fixed universe mismatch")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Missing/nonpositive market prices")
    levels = pd.read_csv(folder / "tracking_levels.csv", parse_dates=["date"], float_precision="round_trip")
    if levels.duplicated(["series_id", "date"]).any() or not np.isfinite(levels.level).all() or (levels.level <= 0).any():
        raise ValueError("Duplicate/missing/nonpositive tracking levels")
    expected_ids = {p[k] for p in meta["pairs"].values() for k in ("etf_series", "benchmark_series")}
    if set(levels.series_id) != expected_ids:
        raise ValueError("Tracking series manifest mismatch")
    for _, frame in levels.groupby("series_id"):
        if not frame.date.is_monotonic_increasing:
            raise ValueError("Tracking dates not ordered")
    return prices, levels, meta


def _write_phase(stage, phase, tables, methodology):
    folder = stage / f"output_phase{phase}"
    table_dir = folder if phase == 3 else folder / "tables"
    table_dir.mkdir(parents=True)
    hashes = {}
    for name in REQUIRED_TABLES[phase]:
        frame = tables[name].copy()
        for col in frame:
            if pd.api.types.is_datetime64_any_dtype(frame[col].dtype):
                frame[col] = frame[col].map(lambda v: None if pd.isna(v) else v.isoformat())
        path = table_dir / (name + ".csv")
        frame.to_csv(path, index=False)
        hashes[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    path = folder / "methodology.json"
    path.write_text(json.dumps(methodology, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (folder / "sha256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


def build_bundle(destination, inputs=None):
    """Recompute all 13 presentation tables in a new CSV/JSON-only directory.

    Returns generation metadata. Refuses existing output, including a partial
    directory. Calculations use all original cases, not a selected best subset.
    """
    destination = Path(destination).resolve()
    inputs = Path(inputs) if inputs is not None else ROOT / "data/research_demo"
    if destination.exists():
        raise FileExistsError("Results already exist; choose a new --output-dir")
    if destination.is_relative_to(inputs.resolve()):
        raise ValueError("Result directory must be outside inputs")
    started = time.perf_counter()
    prices, levels, provenance = load_inputs(inputs)
    returns = simple_returns(prices)
    calendar = china_sessions(prices.index[0], prices.index[-1].to_period("Q").end_time.normalize() + pd.Timedelta(days=20))
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".research-", dir=destination.parent))
    try:
        print("Phase 2: walk-forward portfolios", flush=True)
        tables, meta = run_scenarios(returns)
        _write_phase(stage, 2, tables, meta)
        print("Phase 3: basis-gated Tracking", flush=True)
        series = {k: v.set_index("date").level for k, v in levels.groupby("series_id")}
        results = []
        tracking_calendar = calendar[calendar <= prices.index[-1]]
        for pair_id, p in provenance["pairs"].items():
            e, b = series[p["etf_series"]], series[p["benchmark_series"]]
            bc = tracking_calendar.union(b.index) if p["benchmark"]["code"] == "Au99.99" else tracking_calendar
            r = analyze_pair(pair_id, e, b, p["etf"], p["benchmark"], tracking_calendar, bc, window=63)
            r["summary"].update(ticker=pair_id.split("__")[0], benchmark_code=p["benchmark"]["code"],
                comparison_role=p["benchmark"]["comparison_role"], etf_value_type=p["etf"]["value_type"],
                benchmark_type=p["benchmark"]["benchmark_type"])
            results.append(r)
        _write_phase(stage, 3, {"summary": pd.DataFrame([r["summary"] for r in results]),
            "daily": pd.concat([r["daily"].assign(pair_id=r["summary"]["pair_id"]) for r in results], ignore_index=True)},
            dict(pairs=provenance["pairs"], limitations=provenance["limitations"], normalized_input=True))
        print("Phase 4: rule indices", flush=True)
        rules = load_index_rules()
        tables, meta = run_index_matrix(returns, calendar, rules)
        if meta["failed_scenario_count"]:
            raise ValueError("Index calculation failed; no partial demo published")
        _write_phase(stage, 4, tables, meta)
        print("Phase 5: full predeclared robustness matrix", flush=True)
        tables, meta = run_robustness(returns, calendar, rules["universe"], load_robustness_rules())
        if meta["failed_scenarios"]:
            raise ValueError("Robustness calculation failed; no partial demo published")
        tables.update(build_robustness_reports(tables, meta["rules"]))
        _write_phase(stage, 5, tables, meta)
        file_hash = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        metadata = dict(schema_version=1, sample_id=provenance["sample_id"],
            result_kind="recomputed_normalized_fixed_sample", raw_evidence_included=False,
            scope="Phase1 normalized price validation; Phase2–5 original engines; not the complete raw acquisition/Phase1 audit package",
            created_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.perf_counter() - started,
            input_manifest_sha256=file_hash(inputs / "sha256.json"),
            versions={name: version(name) for name in ["numpy", "pandas", "scipy", "exchange-calendars", "streamlit"]},
            configuration_sha256={p.name: file_hash(p) for p in (ROOT / "config").glob("*.json")},
            engine_sha256={p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")},
            phase2_scenarios=24, phase4_scenarios=4, phase5_successful_scenarios=len(meta["scenarios"]),
            phase5_skipped_scenarios=meta["skipped_scenarios"], limitations=provenance["limitations"])
        (stage / "bundle.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if destination.exists():
            raise FileExistsError("Destination appeared during generation")
        os.rename(stage, destination)
    except Exception:
        if stage.resolve().parent != destination.parent:
            raise ValueError("Unexpected stage path")
        shutil.rmtree(stage)
        raise
    return metadata
