"""Maintainer-only extraction of compact inputs from the original local evidence.

Normal users run build_research_demo.py. This command requires the original
Phase 1 and Phase 3 archives; it never downloads, invents or replaces evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

import pandas as pd

from portfolio_analysis.backtest_reporting import load_phase1_source

ROOT = Path(__file__).resolve().parents[1]


def portable(value):
    """Remove machine-specific file locations while retaining source URLs/hashes."""
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items()
                if k not in {"raw_file", "local_path", "evidence_files", "snapshot_path", "issuer_pdf"}}
    if isinstance(value, list):
        return [portable(v) for v in value]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/research_demo")
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("Destination exists; preserve the published snapshot")
    load_phase1_source(ROOT / "output_phase1")  # verify raw hashes and saved prices
    prices = pd.read_csv(ROOT / "output_phase1/powerbi/prices.csv", float_precision="round_trip")
    market = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    series, pairs, captured = {}, {}, {}
    runner = runpy.run_path(str(ROOT / "scripts/run_phase3.py"))
    original = runner["main"].__globals__["analyze_pair"]

    def capture(pair_id, etf, benchmark, etf_meta, benchmark_meta, etf_calendar, benchmark_calendar, window=63):
        ticker = pair_id.split("__")[0]
        ids = ("etf:" + ticker, "benchmark:" + benchmark_meta["code"])
        for name, values in zip(ids, (etf, benchmark)):
            selected = values.loc["2023-08-14":"2026-08-12"].rename("level")
            if name in series:
                pd.testing.assert_series_equal(series[name], selected)
            series[name] = selected
        pairs[pair_id] = dict(etf_series=ids[0], benchmark_series=ids[1],
                              etf=portable(etf_meta), benchmark=portable(benchmark_meta))
        return original(pair_id, etf, benchmark, etf_meta, benchmark_meta,
                        etf_calendar, benchmark_calendar, window)

    def capture_export(results, target, metadata):
        captured.update(portable(metadata))
        rebuilt = pd.DataFrame([r["summary"] for r in results])
        saved = pd.read_csv(ROOT / "output_phase3/summary.csv", dtype={"benchmark_code": str})
        saved["reasons"] = saved["reasons"].fillna("")  # CSV blank explanatory text
        pd.testing.assert_frame_equal(rebuilt[saved.columns].reset_index(drop=True), saved,
                                      check_dtype=False, rtol=1e-10, atol=1e-12)

    runner["main"].__globals__.update(analyze_pair=capture, export_tracking=capture_export)
    runner["main"](["--output-dir", str(args.output_dir / "not_written")])
    levels = pd.concat([v.rename_axis("date").reset_index().assign(series_id=k)
                        for k, v in series.items()], ignore_index=True)
    market_source = dict(source="Eastmoney", price_basis="forward_adjusted_market_price_NOT_NAV",
                         retrieval_timestamp="unknown_legacy_snapshot", requested_start="2023-08-12",
                         requested_end="2026-08-12", url="https://quote.eastmoney.com/",
                         raw_sha256=prices.groupby("symbol").raw_sha256.first().to_dict())
    metadata = dict(schema_version=1, sample_id="phase1-5-normalized-2026-08-12-v1",
                    raw_evidence_included=False, start="2023-08-14", end="2026-08-12",
                    market_source=market_source, pairs=pairs,
                    sources=captured["source_manifest"], corporate_actions=captured["corporate_actions"],
                    nav_data_quality=captured["nav_data_quality"], limitations=captured["limitations"],
                    transformation="market: verified provider close; ETF: original NAV/cash-reinvestment or E Fund growth parser; benchmark: original index/SGE close parsers; no rounding, imputation or synthetic observations",
                    evidence_scope="Normalized numerical inputs plus source URLs/hashes. Recomputes calculations; original raw response and PDF audit chain are not distributed.")
    args.output_dir.mkdir(parents=True)
    market.to_csv(args.output_dir / "market_prices.csv")
    levels.to_csv(args.output_dir / "tracking_levels.csv", index=False)
    (args.output_dir / "provenance.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output_dir.iterdir()}
    (args.output_dir / "sha256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print("Input files:", hashes.keys())


if __name__ == "__main__":
    main()
