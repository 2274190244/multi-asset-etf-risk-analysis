"""Run the approved Phase 2 matrix from preserved Phase 1 evidence."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
from portfolio_analysis.backtest_reporting import (
    file_hashes, load_phase1_source, run_scenarios, compare_phase1, export_package,
)


def main(argv=None):
    """Read local evidence, validate and publish 24 scenarios; return exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("output_phase1"))
    parser.add_argument("--output-dir", type=Path, default=Path("output_phase2"))
    parser.add_argument("--estimation-window", type=int, default=252)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("Output exists; supply a new --output-dir")
    # Avoid copying output into its own source evidence tree.
    if args.output_dir.resolve().is_relative_to(args.source.resolve()):
        parser.error("Output must be outside the source folder")
    original = file_hashes(args.source)
    audit = Path("docs/audit/phase2")
    audit.mkdir(parents=True, exist_ok=True)
    try:
        returns, source_meta = load_phase1_source(args.source)
        tables, meta = run_scenarios(returns, estimation_window=args.estimation_window,
            risk_free_rate=source_meta["annual_risk_free_rate"])
        tables["phase1_comparison"] = compare_phase1(args.source, tables["daily"],
            source_meta["annual_risk_free_rate"])
        meta.update(generated_at=datetime.now(timezone.utc).isoformat(),
            source_manifest=original, source_folder=str(args.source),
            source_retrieval_timestamp="unknown_legacy_snapshot",
            source_price_basis="forward_adjusted; total-return equivalence not verified",
            source_requested_start=source_meta["requested_start"],
            source_requested_end=source_meta["requested_end"])
        if file_hashes(args.source) != original:
            raise ValueError("Source changed during execution")
        export_package(tables, meta, args.output_dir, source_folder=args.source)
        if file_hashes(args.source) != original:
            raise ValueError("Source changed during export")
    except Exception as error:
        # Failure is explicit and preserves diagnostics; no partial success matrix.
        failure = audit/("failure-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")+".json")
        failure.write_text(json.dumps({"error": str(error), "source_manifest": original}, indent=2), encoding="utf-8")
        print(str(error), file=sys.stderr)
        return 1
    print(f"Complete: {meta['scenario_count']} scenarios, {meta['evaluation_count']} shared returns, {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
