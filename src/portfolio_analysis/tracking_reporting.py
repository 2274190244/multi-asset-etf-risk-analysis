"""Basis-gated tracking reports, without Streamlit dependencies."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import numpy as np
import pandas as pd
from .benchmark_config import assess_comparability
from .tracking import align_levels,tracking_statistics,rolling_tracking

_TRACKING_FIELDS=("tracking_difference","annualized_tracking_difference",
                  "annualized_tracking_error","information_ratio")

def analyze_pair(pair_id,etf,benchmark,etf_metadata,benchmark_metadata,
                 etf_calendar,benchmark_calendar,window=63):
    """Return summary/daily/events/metadata for a level pair and explicit calendars.

    Unavailable histories produce a reason and zero observations. Basis mismatch
    retains descriptive return differences/volatility/drawdown/correlation but
    suppresses TD, TE and IR, including rolling TE. No silent tracking relabel.
    """
    gate=assess_comparability(etf_metadata,benchmark_metadata)
    summary=dict(pair_id=pair_id,status=gate["status"],reasons="; ".join(gate["reasons"]),
                 matched_observation_count=0,**{key:np.nan for key in _TRACKING_FIELDS})
    result=dict(summary=summary,daily=pd.DataFrame(),events=pd.DataFrame(),
                metadata=dict(etf=etf_metadata,benchmark=benchmark_metadata,rolling_window=window))
    if etf is None or benchmark is None or gate["status"]=="unavailable":
        summary.update(status="unavailable",reasons=summary["reasons"] or "Missing input series")
        return result
    try:
        aligned=align_levels(etf,benchmark,etf_calendar,benchmark_calendar)
    except ValueError as exc:
        # Invalid data is not converted to an apparently valid empty study.
        raise ValueError(f"{pair_id}: {exc}") from exc
    e,b=aligned.returns.etf,aligned.returns.benchmark
    stats=tracking_statistics(e,b)
    stats["cumulative_return_difference"]=stats["tracking_difference"]
    stats["annualized_return_difference"]=stats["annualized_tracking_difference"]
    summary.update(stats,**aligned.quality)
    daily=aligned.prices/aligned.prices.iloc[0]-1
    daily=daily.rename(columns={"etf":"etf_cumulative_return","benchmark":"benchmark_cumulative_return"})
    daily["etf_return"]=e;daily["benchmark_return"]=b
    daily["daily_return_difference"]=e-b
    daily["excess_return"]=(e-b) if gate["status"]=="comparable" else np.nan
    rolling=rolling_tracking(e,b,window)
    daily=daily.join(rolling)
    daily["rolling_correlation_status"]=np.where(daily.rolling_correlation.notna(),"ok","insufficient_window_or_zero_variance")
    if gate["status"]!="comparable":
        for key in _TRACKING_FIELDS:summary[key]=np.nan
        summary["information_ratio_status"]="not_comparable"
        daily["rolling_tracking_error"]=np.nan
    summary["short_sample_warning"]=len(e)<252
    result.update(daily=daily.rename_axis("date").reset_index(),events=aligned.events)
    return result

def export_tracking(results,target,metadata):
    """Create a new report directory atomically; never overwrite prior results.

    Inputs: list of analyze_pair results, nonexisting target, JSON metadata.
    Outputs: summary/daily/exclusions CSVs, SQLite, UTF-8 provenance JSON and
    SHA256 manifest. Undefined ratios remain missing and carry status fields.
    """
    target=Path(target)
    if target.exists():raise FileExistsError(f"Preserving existing output: {target}")
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=".phase3-",dir=target.parent))
    try:
        summaries=pd.DataFrame([r["summary"] for r in results])
        daily=[];events=[]
        for r in results:
            if not r["daily"].empty:daily.append(r["daily"].assign(pair_id=r["summary"]["pair_id"]))
            if not r["events"].empty:events.append(r["events"].assign(pair_id=r["summary"]["pair_id"]))
        frames={"summary":summaries,"daily":pd.concat(daily,ignore_index=True) if daily else pd.DataFrame(columns=["pair_id","date"]),
                "exclusions":pd.concat(events,ignore_index=True) if events else pd.DataFrame(columns=["pair_id","date","reason","asset","action"])}
        for key in ("original_etf_data_audit","nav_data_quality","corporate_actions"):
            if metadata.get(key):
                frames[key]=pd.DataFrame(metadata[key]).map(lambda x: json.dumps(x,ensure_ascii=False) if isinstance(x,(list,dict)) else x)
        for name,frame in frames.items():frame.to_csv(stage/(name+".csv"),index=False)
        with closing(sqlite3.connect(stage/"tracking.sqlite")) as connection:
            for name,frame in frames.items():frame.to_sql(name,connection,index=False)
        document=dict(metadata,pairs={r["summary"]["pair_id"]:r["metadata"] for r in results})
        (stage/"metadata.json").write_text(json.dumps(document,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir() if p.is_file()}
        (stage/"sha256.json").write_text(json.dumps(hashes,indent=2),encoding="utf-8")
        os.rename(stage,target)
    except Exception:
        shutil.rmtree(stage)
        raise
    return target
