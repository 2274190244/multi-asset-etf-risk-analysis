"""Audited Phase 4 rule comparisons and independent, timestamp-preserving exports."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import numpy as np
import pandas as pd
from .index_construction import run_index, IndexCalculationError, assumed_availability
from .metrics import annualized_return,annualized_volatility,sharpe_ratio,maximum_drawdown
from .backtest_reporting import file_hashes
from .config import ASSETS
from .data_source import parse_eastmoney_response
from .quality import china_sessions

def load_index_rules(path=None):
    """Load/validate the supported versioned rule configuration; return a dict.

    Only equal/inverse-volatility, actual monthly/quarterly, zero additional cost
    and uncapped concentration are supported. Unsupported settings are rejected.
    """
    path=Path(path) if path else Path(__file__).resolve().parents[2]/"config/index_rules.json"
    rules=json.loads(path.read_text(encoding="utf-8"))
    validate_rules(rules)
    return rules

def validate_rules(rules):
    """Reject unsupported or misleading rule settings; no ignored policy switches."""
    for key,allowed in [("weighting_methods",{"equal_weight","inverse_volatility"}),
                        ("rebalance_frequencies",{"monthly","quarterly"})]:
        if len(rules[key])!=len(allowed) or set(rules[key])!=allowed:raise ValueError("Unsupported "+key)
    fixed={"schema_version":1,"rule_version":"phase4-v1",
        "signal_cutoff":"observation date < execution t; available_at <= t14:59 Asia/Shanghai",
        "execution":"close t; target earns t+1",
        "inception":"first calendar quarter-end after complete estimation window"}
    for key,value in fixed.items():
        if rules.get(key)!=value:raise ValueError("Unsupported fixed policy: "+key)
    window=rules["estimation_window"]
    if isinstance(window,bool) or not isinstance(window,int) or window<2:raise ValueError("Invalid estimation window")
    if rules["annualization_days"]!=252 or rules["transaction_cost_bps"]!=0 or rules["concentration_cap"] is not None:
        raise ValueError("Only 252-day, gross, uncapped indices supported")
    if rules["availability_policy"]!="assumed_next_session_09:00":
        raise ValueError("Unsupported default availability policy")
    if rules["price_basis"]!="forward_adjusted" or rules["total_return_verified"] is not False:
        raise ValueError("Unsupported or unverified return-basis claim")
    if rules["market_cap_weighted"]["status"]!="skipped" or not rules["market_cap_weighted"].get("reason"):
        raise ValueError("Market cap requires a documented skipped status")
    rf=rules["annual_risk_free_rate"]
    if not np.isfinite(rf) or rf<=-1:raise ValueError("Invalid risk-free assumption")

def load_index_source(folder):
    """Verify raw/provider provenance, then retain all requested session rows.

    Returns (daily returns, provenance). Does not use Phase1's selected shared
    window. Asset gaps remain NaN (including the following undefined return);
    events identify them for point-in-time eligibility or held-position failure.
    """
    folder=Path(folder)
    meta=json.loads((folder/"methodology.json").read_text(encoding="utf-8"))
    prices=pd.read_csv(folder/"powerbi/prices.csv",parse_dates=["date"])
    provenance=pd.read_csv(folder/"powerbi/source_metadata.csv")
    if set(prices.symbol)!={a.symbol for a in ASSETS} or set(provenance.symbol)!={a.symbol for a in ASSETS}:
        raise ValueError("Expected fixed five-ETF source universe")
    if prices.duplicated(["date","symbol"]).any():raise ValueError("Duplicate source prices")
    columns=["source","price_basis","retrieval_timestamp","requested_start","requested_end"]
    for frame in (prices,provenance):
        for field in columns+["raw_sha256"]:
            if frame[field].isna().any() or frame[field].astype(str).str.strip().eq("").any():
                raise ValueError("Incomplete source provenance: "+field)
        if not frame.source.eq("eastmoney").all() or not frame.price_basis.eq("forward_adjusted").all():
            raise ValueError("Mixed price source/basis")
    for asset in ASSETS:
        record=provenance[provenance.symbol==asset.symbol]
        saved_rows=prices[prices.symbol==asset.symbol]
        if len(record)!=1:raise ValueError("Ambiguous asset provenance")
        record=record.iloc[0]
        raw=folder/"raw"/("eastmoney_"+asset.symbol+".json")
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=record.raw_sha256:
            raise ValueError("Raw hash mismatch: "+asset.symbol)
        for field in columns+["raw_sha256"]:
            if not saved_rows[field].eq(record[field]).all():
                raise ValueError("Row/source provenance mismatch: "+asset.symbol+" "+field)
        original=parse_eastmoney_response(json.loads(raw.read_text(encoding="utf-8")),asset).set_index("date").close.sort_index()
        original.index=pd.to_datetime(original.index)
        saved=saved_rows.set_index("date").close.sort_index()
        try:
            pd.testing.assert_series_equal(saved,original,check_names=False,check_dtype=False,rtol=1e-12,atol=1e-12)
        except AssertionError as error:raise ValueError("Raw versus saved price mismatch: "+asset.symbol) from error
    start,end=pd.Timestamp(meta["requested_start"]),pd.Timestamp(meta["requested_end"])
    if not provenance.requested_start.eq(str(start.date())).all() or not provenance.requested_end.eq(str(end.date())).all():
        raise ValueError("Requested bounds disagree with raw provenance")
    calendar=china_sessions(start,end)
    wide=prices.pivot(index="date",columns="symbol",values="close").sort_index()
    unexpected=wide.index.difference(calendar)
    if len(unexpected):raise ValueError("Unexpected source calendar dates: "+str(unexpected.tolist()))
    wide=wide.reindex(calendar)
    observed=wide.to_numpy(dtype=float)
    if np.isinf(observed).any() or (observed<=0).any():raise ValueError("Invalid observed source price")
    returns=wide.pct_change(fill_method=None).iloc[1:]
    events=[]
    for kind,frame in (("missing_source_price",wide),("undefined_return_due_to_missing_price",returns)):
        for i,j in zip(*np.where(frame.isna().to_numpy())):
            events.append(dict(date=str(frame.index[i].date()),symbol=str(frame.columns[j]),
                               reason=kind,action="retain_missing_for_point_in_time_policy"))
    return returns,dict(source_folder=str(folder),source_manifest=file_hashes(folder),
        provider_provenance=provenance[["symbol"]+columns+["raw_sha256"]].to_dict("records"),
        first_price_date=str(calendar[0].date()),first_return_date=str(returns.index[0].date()),
        last_date=str(calendar[-1].date()),price_count=len(wide),return_count=len(returns),rows_removed=0,
        missing_price_cells=int(wide.isna().sum().sum()),missing_return_cells=int(returns.isna().sum().sum()),
        quality_events=events,initial_undefined_return_count=1,
        source_sample_policy="full requested session range; ignore inherited shared-window selection; preserve gaps",
        inherited_phase1_methodology=meta)

def run_index_matrix(returns,calendar,rules,available_at=None):
    """Return four rule tables and metadata on identical successful evaluation dates.

    Failed paths retain labelled diagnostic trajectories but receive NO return/
    risk performance statistics. Initial turnover is separate from maintenance;
    annualized maintenance turnover=sum*252/evaluation_return_count.
    """
    validate_rules(rules)
    frames={name:[] for name in ("daily","holdings","rebalances","components","eligibility")}
    summaries=[];failures=[];details={};common=None;weight_summaries=[]
    for strategy in rules["weighting_methods"]:
        for frequency in rules["rebalance_frequencies"]:
            name=strategy+"__"+frequency
            failed=None
            try:
                result=run_index(returns,calendar,rules["universe"],strategy=strategy,frequency=frequency,
                    estimation_window=rules["estimation_window"],base_level=rules["base_level"],available_at=available_at)
            except IndexCalculationError as error:
                result=error.partial;failed=error.diagnostics
                failures.append(dict(index_id=name,**failed))
            status="failed" if failed else "complete"
            details[name]=dict(result.metadata,diagnostics=failed)
            row=dict(index_id=name,strategy=strategy,frequency=frequency,status=status,
                annualized_return=np.nan,annualized_volatility=np.nan,sharpe_ratio=np.nan,
                maximum_drawdown=np.nan,cumulative_return=np.nan,evaluation_count=0)
            if not failed:
                if common is None:common=result.daily.index
                elif not common.equals(result.daily.index):raise ValueError("Index evaluation dates differ")
                # Exactly one structural initial undefined return; no generic dropna.
                daily=result.daily.iloc[1:]
                values=daily.index_return
                if values.isna().any():raise ValueError("Missing successful index returns")
                ledger=result.rebalances
                maintenance=ledger.loc[~ledger.initial,"turnover"]
                sigma=annualized_volatility(values)
                sharpe=sharpe_ratio(values,rules["annual_risk_free_rate"])
                row.update(cumulative_return=float(result.daily.index_level.iloc[-1]/rules["base_level"]-1),
                    annualized_return=annualized_return(values),annualized_volatility=sigma,
                    sharpe_ratio=sharpe,sharpe_status="ok" if np.isfinite(sharpe) else "undefined_zero_volatility",
                    maximum_drawdown=maximum_drawdown(values),evaluation_count=len(values),
                    inception=result.metadata["inception"],first_return_date=result.metadata["first_return_date"],
                    end_date=result.metadata["end_date"],initial_undefined_return_count=1,
                    initial_turnover=float(ledger.loc[ledger.initial,"turnover"].sum()),
                    maintenance_rebalances=len(maintenance),maintenance_turnover=float(maintenance.sum()),
                    annualized_maintenance_turnover=float(maintenance.sum()*252/len(values)),
                    average_rebalance_turnover=float(maintenance.mean()) if len(maintenance) else np.nan,
                    maximum_weight=float(daily.maximum_weight.max()),average_hhi=float(daily.hhi.mean()),
                    maximum_hhi=float(daily.hhi.max()),
                    maximum_pretrade_weight=float(result.holdings.pretrade_weight.max()),
                    maximum_target_weight=float(ledger.target_maximum_weight.max()),
                    maximum_target_hhi=float(ledger.target_hhi.max()))
                h=result.holdings[result.holdings.date>result.daily.index[0]]
                for symbol,g in h.groupby("symbol"):
                    last=result.targets[result.targets.symbol==symbol].iloc[-1]
                    weight_summaries.append(dict(index_id=name,symbol=symbol,
                        average_end_weight=float(g.end_weight.mean()),minimum_end_weight=float(g.end_weight.min()),
                        maximum_end_weight=float(g.end_weight.max()),maximum_pretrade_weight=float(g.pretrade_weight.max()),
                        last_target_weight=float(last.target_weight),last_end_weight=float(g.end_weight.iloc[-1])))
            summaries.append(row)
            for key,frame in [("daily",result.daily.reset_index()),("holdings",result.holdings),
                              ("rebalances",result.rebalances),("components",result.targets),("eligibility",result.eligibility)]:
                if not frame.empty:frames[key].append(frame.assign(index_id=name,path_status=status))
    tables={key:pd.concat(values,ignore_index=True) if values else pd.DataFrame(columns=["index_id","path_status"])
            for key,values in frames.items()}
    tables["summary"]=pd.DataFrame(summaries)
    tables["failures"]=pd.DataFrame(failures,columns=["index_id","date","reason","affected_assets"])
    tables["weight_summary"]=pd.DataFrame(weight_summaries,columns=["index_id","symbol","average_end_weight",
        "minimum_end_weight","maximum_end_weight","maximum_pretrade_weight","last_target_weight","last_end_weight"])
    comparisons=[]
    for strategy in rules["weighting_methods"]:
        subset=tables["summary"].query("strategy==@strategy and status=='complete'").set_index("frequency")
        if set(subset.index)=={"monthly","quarterly"}:
            comparisons.append(dict(strategy=strategy,**{metric:float(subset.loc["monthly",metric]-subset.loc["quarterly",metric])
                for metric in ("cumulative_return","annualized_return","annualized_volatility","sharpe_ratio",
                               "maximum_drawdown","maintenance_turnover","annualized_maintenance_turnover",
                               "maximum_weight","average_hhi")}))
    tables["monthly_vs_quarterly"]=pd.DataFrame(comparisons) if comparisons else pd.DataFrame(columns=["strategy"])
    tables["unavailable_indices"]=pd.DataFrame([dict(index_id="market_cap_weighted",**rules["market_cap_weighted"])])
    availability=assumed_availability(returns,calendar) if available_at is None else available_at
    tables["data_availability"]=pd.concat([pd.DataFrame({"date":returns.index,"symbol":s,"available_at":availability[s].to_numpy()})
                                           for s in returns],ignore_index=True)
    metadata=dict(generated_at=datetime.now(timezone.utc).isoformat(),rules=rules,
        market_cap_weighted=rules["market_cap_weighted"],scenario_count=4,
        failed_scenario_count=len(failures),scenarios=details,
        comparison_difference="monthly minus quarterly; identical return dates",
        concentration_convention="Daily close post-rebalance weights; pretrade peak separately reported",
        sharpe_convention="annual effective RF -> (1+RF)^(1/252)-1; daily excess mean/sample std * sqrt(252)",
        availability_evidence="assumed" if available_at is None else "caller_supplied_not_independently_certified")
    return tables,metadata

def export_index_package(tables,metadata,destination,source_folder=None):
    """Create timestamp-preserving CSV/SQLite/JSON package in a NEW directory.

    Successful atomic rename only; optional source folder is copied verbatim for
    replay. Existing destinations rejected. Cleanup touches only our owned stage.
    """
    destination=Path(destination)
    if destination.exists():raise ValueError("Output exists; use a new version")
    if any(not name.replace("_","").isalnum() for name in tables):raise ValueError("Invalid table name")
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=".phase4-",dir=destination.parent))
    try:
        (stage/"tables").mkdir()
        with closing(sqlite3.connect(stage/"analysis.sqlite")) as connection:
            for name,table in tables.items():
                serialized=table.copy()
                for col in serialized:
                    if pd.api.types.is_datetime64_any_dtype(serialized[col].dtype):
                        serialized[col]=serialized[col].map(lambda v: None if pd.isna(v) else v.isoformat())
                    elif serialized[col].dtype==object:
                        serialized[col]=serialized[col].map(lambda v:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v)
                serialized.to_csv(stage/"tables"/(name+".csv"),index=False)
                serialized.to_sql(name,connection,index=False,if_exists="fail")
        if source_folder is not None:shutil.copytree(source_folder,stage/"input_phase1")
        (stage/"methodology.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
        (stage/"sha256.json").write_text(json.dumps(file_hashes(stage),indent=2),encoding="utf-8")
        if destination.exists():raise ValueError("Output exists; use a new version")
        os.rename(stage,destination)
    except Exception:
        if stage.resolve().parent!=destination.parent.resolve():raise ValueError("Unexpected staging path")
        shutil.rmtree(stage)
        raise
    return destination
