"""Predeclared, common-date robustness experiments without parameter selection."""
import itertools
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .backtest import run_backtest
from .index_construction import run_index,rebalance_dates
from .metrics import annualized_return,annualized_volatility,sharpe_ratio,maximum_drawdown

PERFORMANCE=("cumulative_return","annualized_return","annualized_volatility","sharpe_ratio","maximum_drawdown")

def load_robustness_rules(path=None):
    """Load a versioned, predeclared comparison grid; no performance-based choices."""
    path=Path(path) if path else Path(__file__).resolve().parents[2]/"config/robustness_rules.json"
    rules=json.loads(path.read_text(encoding="utf-8"))
    validate_robustness_rules(rules)
    return rules

def validate_robustness_rules(c):
    """Reject unsupported windows, duplicate scenarios and inconsistent period bounds."""
    if c.get("schema_version")!=1 or c.get("parameter_selection")!="none":
        raise ValueError("Unsupported schema or parameter selection")
    for key,allowed in [("windows",{126,252,504}),("engines",{"phase2","phase4"}),
                       ("phase2_strategies",{"equal_weight","minimum_variance","inverse_volatility"}),
                       ("phase4_strategies",{"equal_weight","inverse_volatility"}),
                       ("frequencies",{"monthly","quarterly"}),("cost_bps",{0,5,10,20})]:
        values=c[key]
        if not values or any(isinstance(x,bool) for x in values) or len(values)!=len(set(values)) or not set(values)<=allowed:
            raise ValueError("Invalid "+key)
    if set(c["frequencies"])!={"monthly","quarterly"}:raise ValueError("Both frequencies required")
    n=c["minimum_period_observations"]
    if isinstance(n,bool) or not isinstance(n,int) or n<2:raise ValueError("Invalid minimum observations")
    if not np.isfinite(c["annual_risk_free_rate"]) or c["annual_risk_free_rate"]<=-1:raise ValueError("Invalid RF")
    if not np.isfinite(c["bond_concentration_threshold"]) or not 0<c["bond_concentration_threshold"]<=1:
        raise ValueError("Invalid concentration threshold")
    names=[g["group_id"] for g in c["groups"]]
    if not names or len(set(names))!=len(names):raise ValueError("Duplicate/empty groups")
    for g in c["groups"]:
        anchor,end=pd.Timestamp(g["inception_date"]),pd.Timestamp(g["end_date"])
        if pd.isna(anchor) or pd.isna(end) or anchor>=end:raise ValueError("Invalid group dates")
        ids=[p["period_id"] for p in g["periods"]]
        if len(ids)!=len(set(ids)) or "full" not in ids:raise ValueError("Unique periods including full required")
        for p in g["periods"]:
            lo,hi=pd.Timestamp(p["start"]),pd.Timestamp(p["end"])
            if pd.isna(lo) or pd.isna(hi) or not anchor<lo<=hi<=end:raise ValueError("Invalid subperiod")
        full=next(p for p in g["periods"] if p["period_id"]=="full")
        if pd.Timestamp(full["end"])!=end:raise ValueError("Full period must end at group end")

def _empty_metrics():
    return {basis+"_"+metric:np.nan for basis in ("gross","net") for metric in PERFORMANCE}

def score_period(daily,holdings,trades,targets,dates,risk_free_rate,threshold,minimum_observations,net_available):
    """Score an exact date slice of a CONTINUOUS path, without reinitializing holdings.

    Rebase performance/MDD to wealth1 at the preceding close. Only the first
    global return receives initial cost/turnover attribution. Maintenance trades
    use actual execution dates. Cash costs divided by subperiod starting NAV.
    Bond concentration reports closing weights and the minimum across start,
    pretrade and closing weights; active target preceding the slice is included.
    """
    dates=pd.DatetimeIndex(dates)
    row=dict(status="ok",reason="",evaluation_count=len(dates),**_empty_metrics())
    if len(dates)<minimum_observations:
        row.update(status="insufficient_evaluation",reason=f"Need {minimum_observations} observations; have {len(dates)}")
        return row
    if not dates.is_unique or not dates.is_monotonic_increasing or not dates.isin(daily.index).all():
        raise ValueError("Requested evaluation dates missing/duplicated")
    d=daily.loc[dates]
    for basis in ("gross","net"):
        if basis=="net" and not net_available:continue
        r=d[basis+"_return"]
        if not np.isfinite(r.to_numpy()).all():raise ValueError("Missing performance returns")
        row.update({basis+"_cumulative_return":float(np.expm1(np.log1p(r).sum())),
            basis+"_annualized_return":annualized_return(r),
            basis+"_annualized_volatility":annualized_volatility(r),
            basis+"_sharpe_ratio":sharpe_ratio(r,risk_free_rate),
            basis+"_maximum_drawdown":maximum_drawdown(r)})
        row[basis+"_sharpe_status"]="ok" if np.isfinite(row[basis+"_sharpe_ratio"]) else "undefined_zero_volatility"
    row["net_status"]="modelled" if net_available else "not_modelled_for_index"
    lo,hi=dates[0],dates[-1]
    t=trades[(trades.execution_date>=lo)&(trades.execution_date<=hi)&~trades.initial]
    initial=bool(daily.index[0] in dates)
    maintenance=float(t.turnover.sum())
    row.update(first_return_date=str(lo.date()),end_date=str(hi.date()),
        maintenance_turnover=maintenance,annualized_maintenance_turnover=maintenance*252/len(d),
        maintenance_trade_count=len(t),initial_turnover=float(trades.loc[trades.initial,"turnover"].sum()) if initial else 0.,
        short_sample_warning=len(d)<126,less_than_one_252_day_year=len(d)<252)
    if net_available:
        position=daily.index.get_loc(lo)
        start_nav=1. if position==0 else float(daily.net_nav.iloc[position-1])
        row.update(initial_transaction_cost=float(d.initial_transaction_cost.sum()),
            transaction_cost=float(d.transaction_cost.sum()),
            transaction_cost_fraction_of_start_nav=float(d.transaction_cost.sum()/start_nav),
            cumulative_cost_drag=row["gross_cumulative_return"]-row["net_cumulative_return"])
    else:
        row.update(initial_transaction_cost=0.,transaction_cost=np.nan,
                   transaction_cost_fraction_of_start_nav=np.nan,cumulative_cost_drag=np.nan)
    h=holdings[holdings.date.isin(dates)]
    end_weights=h.pivot(index="date",columns="symbol",values="end_weight").reindex(dates)
    if end_weights.isna().any().any() or not np.allclose(end_weights.sum(axis=1),1,atol=1e-8,rtol=0):
        raise ValueError("Missing/nonbudget holdings in evaluation")
    if "511010.SS" not in end_weights:raise ValueError("Government bond constituent required")
    bond=end_weights["511010.SS"]
    all_bond=h[h.symbol=="511010.SS"].set_index("date").reindex(dates)[["start_weight","pretrade_weight","end_weight"]]
    row.update(maximum_weight=float(end_weights.max(axis=1).max()),
        average_hhi=float((end_weights**2).sum(axis=1).mean()),maximum_hhi=float((end_weights**2).sum(axis=1).max()),
        bond_daily_min=float(bond.min()),bond_daily_mean=float(bond.mean()),bond_daily_median=float(bond.median()),
        bond_daily_max=float(bond.max()),bond_fraction_ge_threshold=float((bond>=threshold).mean()),
        bond_all_states_min=float(all_bond.min(axis=1).min()))
    active_dates=list(targets.loc[(targets.execution_date>=lo)&(targets.execution_date<=hi),"execution_date"].unique())
    prior=targets.loc[targets.execution_date<lo,"execution_date"]
    if len(prior):active_dates.append(prior.max())
    active=targets[targets.execution_date.isin(active_dates)&(targets.symbol=="511010.SS")].target_weight
    row.update(active_target_count=len(active),bond_target_min=float(active.min()),
               bond_target_max=float(active.max()),bond_target_fraction_ge_threshold=float((active>=threshold).mean()))
    return row

def _run_path(returns,calendar,universe,spec):
    if spec["engine"]=="phase2":
        r=run_backtest(returns,strategy=spec["strategy"],estimation_window=spec["window"],
                       rebalance_every=21 if spec["frequency"]=="monthly" else 63,
                       cost_bps=spec["cost_bps"],inception_date=spec["inception"])
        return r.daily,r.weights,r.trades,r.targets,pd.DataFrame(),r.metadata
    r=run_index(returns,calendar,universe,strategy=spec["strategy"],frequency=spec["frequency"],
                estimation_window=spec["window"],inception_date=spec["inception"])
    d=r.daily.iloc[1:].rename(columns={"index_return":"gross_return","index_level":"gross_nav"}).copy()
    d["gross_nav"]/=r.metadata["base_level"]
    d["net_return"]=np.nan;d["net_nav"]=np.nan
    d["transaction_cost"]=0.;d["initial_transaction_cost"]=0.
    return d,r.holdings[r.holdings.date>pd.Timestamp(spec["inception"])],r.rebalances,r.targets,r.eligibility,r.metadata

def run_robustness(returns,calendar,universe,rules):
    """Return predeclared scenarios, continuous paths, sensitivity and metadata.

    Every group has one fixed initialization and evaluation date index. All three
    requested windows remain in the output; insufficient history is a labelled
    skip, never a shortened window or shifted start. Exceptions become failed
    scenario rows, never successful partial performance. No parameter selected.
    """
    validate_robustness_rules(rules)
    if not returns.index.is_unique or not returns.index.is_monotonic_increasing:raise ValueError("Invalid input dates")
    expected=calendar[(calendar>=returns.index[0])&(calendar<=returns.index[-1])]
    if not returns.index.equals(expected):raise ValueError("Input calendar rows missing")
    rows=[];scenarios=[];details={}
    collected={key:[] for key in ("daily","holdings","trades","targets","eligibility")}
    for g in rules["groups"]:
        anchor,end=pd.Timestamp(g["inception_date"]),pd.Timestamp(g["end_date"])
        data=returns.loc[:end]
        evaluation=calendar[(calendar>anchor)&(calendar<=end)]
        coverage_missing=not evaluation.isin(data.index).all() or calendar[-1]<end
        full=next(p for p in g["periods"] if p["period_id"]=="full")
        if not evaluation.equals(evaluation[evaluation>=pd.Timestamp(full["start"])]):
            raise ValueError("Full period cannot silently trim the common evaluation start")
        for engine in rules["engines"]:
            strategies=rules[engine+"_strategies"]
            costs=rules["cost_bps"] if engine=="phase2" else [0]
            for strategy,window,frequency,cost in itertools.product(strategies,rules["windows"],rules["frequencies"],costs):
                name=f"{g['group_id']}__{engine}__{strategy}__w{window}__{frequency}__c{cost}"
                spec=dict(scenario_id=name,group_id=g["group_id"],engine=engine,strategy=strategy,window=window,
                    frequency=frequency,cost_bps=cost,inception=str(anchor.date()),
                    frequency_convention="21/63_sessions" if engine=="phase2" else "calendar_month/quarter")
                available=int((data.index<anchor).sum())
                status="ok";reason=""
                if anchor not in data.index or available<window:
                    status="insufficient_history";reason=f"Need {window} returns before {anchor.date()}; have {available}"
                elif coverage_missing:
                    status="insufficient_evaluation";reason="Requested evaluation endpoint/sessions unavailable"
                elif len(evaluation)<rules["minimum_period_observations"]:
                    status="insufficient_evaluation";reason="Common evaluation sample too short"
                path=None;period_scores={}
                if status=="ok":
                    try:
                        path=_run_path(data,calendar,universe,spec)
                        daily,holdings,trades,targets,eligibility,metadata=path
                        if not daily.index.equals(evaluation):raise ValueError("Common evaluation dates differ")
                        if not (trades.estimation_end<trades.execution_date).all():
                            raise ValueError("Look-ahead estimation boundary")
                        for period in g["periods"]:
                            selected=evaluation[(evaluation>=pd.Timestamp(period["start"]))&(evaluation<=pd.Timestamp(period["end"]))]
                            period_scores[period["period_id"]]=score_period(daily,holdings,trades,targets,selected,
                                rules["annual_risk_free_rate"],rules["bond_concentration_threshold"],
                                rules["minimum_period_observations"],engine=="phase2")
                        details[name]=metadata
                    except ValueError as error:
                        status="failed";reason=str(error);path=None
                scenarios.append(dict(spec,status=status,reason=reason,available_history=available,
                    expected_evaluation_count=len(evaluation)))
                if path is not None:
                    for key,frame in zip(collected,[daily.rename_axis("date").reset_index(),holdings,trades,targets,eligibility]):
                        if not frame.empty:collected[key].append(frame.assign(scenario_id=name))
                for p in g["periods"]:
                    dates=evaluation[(evaluation>=pd.Timestamp(p["start"]))&(evaluation<=pd.Timestamp(p["end"]))]
                    result=dict(spec,period_id=p["period_id"],requested_start=p["start"],requested_end=p["end"],
                                status=status,reason=reason,evaluation_count=0,expected_evaluation_count=len(dates),available_history=available,**_empty_metrics())
                    if path is not None:
                        result.update(period_scores[p["period_id"]])
                    rows.append(result)
    tables={key:pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=["scenario_id"])
            for key,frames in collected.items()}
    tables["scenarios"]=pd.DataFrame(scenarios);tables["sensitivity"]=pd.DataFrame(rows)
    metadata=dict(rules=rules,scenarios=details,parameter_selection="none",
        availability_policy="prior dated closes; next-session09:00 availability assumption, not original publication proof",
        independent_trials=False,subperiod_policy="continuous holdings; rebase metrics only; do not restart",
        concentration_scope="closing and all-state bond weights; active prior target included",
        initial_cost_policy="first global return only, inherited Phase2; maintenance ledger separate",
        failed_scenarios=sum(x["status"]=="failed" for x in scenarios),
        skipped_scenarios=sum(x["status"].startswith("insufficient") for x in scenarios))
    return tables,metadata
