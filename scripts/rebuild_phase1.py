"""Rebuild Phase 1 from immutable legacy raw evidence; never overwrite packages."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
from datetime import date, datetime, timezone
import numpy as np
import pandas as pd
from portfolio_analysis.config import ASSETS
from portfolio_analysis.data_source import parse_eastmoney_response
from portfolio_analysis.metrics import asset_metrics
from portfolio_analysis.portfolios import minimum_volatility_weights, portfolio_returns
from portfolio_analysis.pipeline import run_pipeline

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,default=Path("output_phase1"))
    args=parser.parse_args()
    old=Path("output_verified"); audit=Path("docs/audit")
    audit.mkdir(parents=True,exist_ok=True)
    hashes={str(p.relative_to(old)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(old.rglob("*")) if p.is_file()}
    archive=audit/"output_verified_before.zip"
    manifest=audit/"output_verified_before_sha256.json"
    if not archive.exists():
        with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED) as z:
            for name in hashes: z.write(old/name,arcname=name)
        manifest.write_text(json.dumps(hashes,indent=2),encoding="utf-8")
    elif json.loads(manifest.read_text())!=hashes:
        raise ValueError("Legacy evidence changed since archival")
    if args.output_dir.exists():
        raise ValueError("Output exists; supply a new --output-dir")
    preserved = Path("output_phase1")
    source_manifest = pd.read_csv(preserved / "powerbi/source_metadata.csv").set_index("symbol")
    frames=[]
    now=datetime.now(timezone.utc).isoformat()
    for asset in ASSETS:
        path=preserved / "raw" / f"eastmoney_{asset.symbol}.json"
        expected_hash=source_manifest.loc[asset.symbol,"raw_sha256"]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:
            raise ValueError(f"Preserved raw hash mismatch: {asset.symbol}")
        frame=parse_eastmoney_response(json.loads(path.read_text(encoding="utf-8")),asset)
        frame["retrieval_timestamp"]="unknown_legacy_snapshot"
        frame["requested_start"]="2023-08-12";frame["requested_end"]="2026-08-12"
        frame["raw_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
        frame["snapshot_path"]=path.as_posix();frame["replay_timestamp"]=now
        frames.append(frame)
    prices=pd.concat(frames,ignore_index=True)
    expected_prices=pd.read_csv(old / "powerbi/prices.csv",parse_dates=["date"])
    keys=["symbol","date","close"]
    pd.testing.assert_frame_equal(
        prices[keys].sort_values(["symbol","date"]).reset_index(drop=True),
        expected_prices[keys].sort_values(["symbol","date"]).reset_index(drop=True),
        check_dtype=False,rtol=0,atol=0)
    result=run_pipeline(date(2023,8,12),date(2026,8,12),args.output_dir,price_data=prices)
    if result.metadata["status"]!="complete":
        raise ValueError(result.metadata)
    # Full-sample repaired result is diagnostic, NOT out-of-sample evidence.
    wide=prices.pivot(index="date",columns="symbol",values="close").sort_index()
    returns=wide.pct_change(fill_method=None).iloc[1:]
    w=minimum_volatility_weights(returns)
    repaired=asset_metrics(pd.DataFrame({"minimum_volatility":portfolio_returns(returns,w)})).iloc[0]
    before=pd.read_csv(old/"powerbi/portfolio_metrics.csv").set_index("portfolio").loc["minimum_volatility"]
    after=pd.read_csv(args.output_dir/"powerbi/portfolio_metrics.csv").set_index("portfolio").loc["minimum_volatility"]
    old_weights=pd.read_csv(old/"powerbi/portfolio_weights.csv").query("portfolio=='minimum_volatility'").set_index("symbol").weight
    new_weights=pd.read_csv(args.output_dir/"powerbi/portfolio_weights.csv").query("portfolio=='minimum_volatility'").set_index("symbol").weight
    rows=[]
    for label,metrics,weights,start,end in [
        ("before_legacy_full_sample",before,old_weights,str(returns.index.min().date()),str(returns.index.max().date())),
        ("after_full_sample_diagnostic_NOT_OOS",repaired,w,str(returns.index.min().date()),str(returns.index.max().date())),
        ("after_train_evaluation",after,new_weights,result.metadata["evaluation_start"],result.metadata["evaluation_end"])]:
        row=dict(scenario=label,sample_start=start,sample_end=end,**metrics.to_dict())
        row.update({f"weight_{s}":float(weights[s]) for s in returns.columns});rows.append(row)
    comparison=pd.DataFrame(rows)
    comparison.to_csv(args.output_dir/"before_vs_after.csv",index=False)
    # Control: evaluate both old EW weights and trained MV weights on the SAME evaluation dates.
    evaluation=returns.loc[result.metadata["evaluation_start"]:result.metadata["evaluation_end"]]
    control=asset_metrics(pd.DataFrame({"legacy_equal_weights":portfolio_returns(evaluation,old_weights),
                                      "trained_minimum_variance":portfolio_returns(evaluation,new_weights)}))
    control.to_csv(args.output_dir/"same_evaluation_control.csv",index_label="portfolio")
    if hashes!={str(p.relative_to(old)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(old.rglob("*")) if p.is_file()}:
        raise AssertionError("Original output_verified was modified")
    print(comparison.to_string(index=False))
    print(json.dumps(result.metadata,ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
