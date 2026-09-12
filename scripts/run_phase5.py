"""Reproduce predeclared Phase 5 robustness analysis from archived prices."""
import argparse
import hashlib
from pathlib import Path
import pandas as pd
from portfolio_analysis.robustness import load_robustness_rules,run_robustness
from portfolio_analysis.robustness_reporting import build_robustness_reports
from portfolio_analysis.index_reporting import load_index_source,load_index_rules,export_index_package
from portfolio_analysis.quality import china_sessions

def main(argv=None):
    """Run all predeclared cases and export a new immutable output directory."""
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,default=Path("output_phase1"))
    p.add_argument("--rules",type=Path,default=Path("config/robustness_rules.json"))
    p.add_argument("--output-dir",type=Path,default=Path("output_phase5"))
    a=p.parse_args(argv)
    if a.output_dir.exists():p.error("Output exists; choose a new directory")
    if a.output_dir.resolve().is_relative_to(a.source.resolve()):p.error("Output inside source")
    rules=load_robustness_rules(a.rules)
    returns,source=load_index_source(a.source)
    end=max(pd.Timestamp(g["end_date"]) for g in rules["groups"])
    calendar=china_sessions(returns.index[0],end.to_period("Q").end_time.normalize()+pd.Timedelta(days=20))
    universe=load_index_rules()["universe"]
    tables,metadata=run_robustness(returns,calendar,universe,rules)
    tables.update(build_robustness_reports(tables,rules))
    tables["source_quality_events"]=pd.DataFrame(source["quality_events"],columns=["date","symbol","reason","action"])
    tables["universe"]=pd.DataFrame(universe)
    metadata.update(source=source,rules_sha256=hashlib.sha256(a.rules.read_bytes()).hexdigest(),
                    calendar_source="exchange_calendars XSHG",comparison_policy="within group and period only")
    export_index_package(tables,metadata,a.output_dir,source_folder=a.source)
    print(tables["scenarios"].groupby(["group_id","status"]).size().to_string())
    print("Output:",a.output_dir)
    return int(metadata["failed_scenarios"]>0)

if __name__=="__main__":raise SystemExit(main())
