"""Reproduce Phase 4 fixed-ETF rule indices from archived prices, without network."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd
from portfolio_analysis.index_reporting import (
    load_index_rules,load_index_source,run_index_matrix,export_index_package)
from portfolio_analysis.backtest_reporting import file_hashes
from portfolio_analysis.quality import china_sessions

def main(argv=None):
    """Validate raw source, run four indices, publish a new package; return exit status."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=Path("output_phase1"))
    parser.add_argument("--rules",type=Path,default=Path("config/index_rules.json"))
    parser.add_argument("--output-dir",type=Path,default=Path("output_phase4"))
    args=parser.parse_args(argv)
    if args.output_dir.exists():parser.error("Output exists; supply a new --output-dir")
    if args.output_dir.resolve().is_relative_to(args.source.resolve()):
        parser.error("Output must be outside the source folder")
    original=file_hashes(args.source)
    try:
        rules=load_index_rules(args.rules)
        returns,source=load_index_source(args.source)
        # Calendar lookahead defines public scheduled boundaries, not future signals.
        calendar_end=returns.index[-1].to_period("Q").end_time.normalize()+pd.Timedelta(days=20)
        calendar=china_sessions(returns.index[0],calendar_end)
        tables,metadata=run_index_matrix(returns,calendar,rules)
        tables["source_quality_events"]=pd.DataFrame(source["quality_events"],
            columns=["date","symbol","reason","action"])
        tables["universe"]=pd.DataFrame(rules["universe"])
        metadata.update(source=source,calendar_source="exchange_calendars XSHG",
            calendar_start=str(calendar[0].date()),calendar_end=str(calendar[-1].date()),
            rules_source=str(args.rules),rules_sha256=hashlib.sha256(args.rules.read_bytes()).hexdigest())
        if file_hashes(args.source)!=original:raise ValueError("Source changed during calculation")
        export_index_package(tables,metadata,args.output_dir,source_folder=args.source)
        if file_hashes(args.source)!=original:raise ValueError("Source changed during export")
    except Exception as error:
        audit=Path("docs/audit/phase4");audit.mkdir(parents=True,exist_ok=True)
        path=audit/("failure-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")+".json")
        path.write_text(json.dumps(dict(error=str(error),source_manifest=original),indent=2),encoding="utf-8")
        print(str(error),file=sys.stderr)
        return 1
    print(tables["summary"].to_string(index=False))
    print("Market cap weighted: skipped — no verified historical size series.")
    print("Output:",args.output_dir)
    return 1 if metadata["failed_scenario_count"] else 0

if __name__=="__main__":raise SystemExit(main())
