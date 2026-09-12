"""Paired, descriptive robustness reports; never select an optimal parameter."""
import numpy as np
import pandas as pd

def build_robustness_reports(tables,rules):
    """Validate actual common dates and return paired deltas and window ranges.

    Inputs are run_robustness tables and predeclared rules. Outputs are DataFrames.
    Differences are monthly minus quarterly or inverse volatility minus equal
    weight. Counts describe overlapping cases, not independent statistical trials.
    """
    s=tables["sensitivity"]
    if s.duplicated(["scenario_id","period_id"]).any():raise ValueError("Duplicate sensitivity rows")
    for _,group in s[s.status=="ok"].groupby(["group_id","period_id"]):
        reference=None
        for row in group.itertuples():
            d=tables["daily"]
            dates=pd.DatetimeIndex(d.loc[(d.scenario_id==row.scenario_id)&
                (d.date>=pd.Timestamp(row.requested_start))&(d.date<=pd.Timestamp(row.requested_end)),"date"])
            if len(dates)!=row.evaluation_count or not dates.is_unique:raise ValueError("Evaluation count/duplicates mismatch")
            if reference is not None and not dates.equals(reference):raise ValueError("Common evaluation dates mismatch")
            reference=dates
    pairs=[]
    keys=["group_id","period_id","engine","strategy","window","cost_bps"]
    for key,g in s.groupby(keys):
        a=g[g.frequency=="monthly"];b=g[g.frequency=="quarterly"]
        if len(a)!=1 or len(b)!=1:raise ValueError("Missing/duplicate frequency")
        a,b=a.iloc[0],b.iloc[0]
        for basis in (["gross","net"] if a.engine=="phase2" else ["gross"]):
            row=dict(zip(keys,key),basis=basis,status="ok" if a.status==b.status=="ok" else "not_comparable",
                     reason="; ".join(x for x in [a.reason,b.reason] if x))
            if row["status"]=="ok":
                for metric in ["annualized_return","annualized_volatility","sharpe_ratio","maximum_drawdown"]:
                    row[metric+"_delta"]=a[basis+"_"+metric]-b[basis+"_"+metric]
                for metric in ["annualized_maintenance_turnover","average_hhi","maximum_weight","bond_daily_mean"]:
                    row[metric+"_delta"]=a[metric]-b[metric]
            pairs.append(row)
    risk=[]
    keys2=["group_id","period_id","engine","window","frequency"]
    for key,g in s[s.cost_bps==0].groupby(keys2):
        a=g[g.strategy=="inverse_volatility"];b=g[g.strategy=="equal_weight"]
        if a.empty or b.empty:continue
        a,b=a.iloc[0],b.iloc[0]
        row=dict(zip(keys2,key),status="ok" if a.status==b.status=="ok" else "not_comparable")
        if row["status"]=="ok":
            for m in ["annualized_volatility","annualized_return","sharpe_ratio","maximum_drawdown"]:
                row[m+"_delta"]=a["gross_"+m]-b["gross_"+m]
        risk.append(row)
    ranges=[]
    keys3=["group_id","period_id","engine","strategy","frequency","cost_bps"]
    for key,g in s.groupby(keys3):
        valid=g[g.status=="ok"]
        for basis in (["gross","net"] if key[2]=="phase2" else ["gross"]):
            row=dict(zip(keys3,key),basis=basis,requested_windows=len(g),valid_windows=len(valid),
                     skipped_or_failed_windows=len(g)-len(valid),status="ok" if len(valid)>=2 else "insufficient_comparison")
            for metric in ["annualized_return","annualized_volatility","sharpe_ratio","maximum_drawdown"]:
                values=valid[basis+"_"+metric]
                for suffix,value in [("min",values.min()),("max",values.max()),("spread",values.max()-values.min())]:
                    row[metric+"_"+suffix]=value
            for metric in ["average_hhi","maximum_weight","bond_daily_mean"]:
                row[metric+"_spread"]=valid[metric].max()-valid[metric].min()
            ranges.append(row)
    freq=pd.DataFrame(pairs);risk=pd.DataFrame(risk);stability=[]
    for group,g in s[(s.strategy=="minimum_variance")&(s.cost_bps==0)&(s.period_id=="full")].groupby("group_id"):
        v=g[g.status=="ok"];minimum=min(v.bond_all_states_min.min(),v.bond_target_min.min()) if len(v) else np.nan
        stability.append(dict(group_id=group,question="minimum_variance_bond_concentration",valid_cases=len(v),
            unavailable_cases=len(g)-len(v),minimum=minimum,threshold=rules["bond_concentration_threshold"],
            conclusion="consistent_in_available_paths" if minimum>=rules["bond_concentration_threshold"] else "not_universal"))
    if not risk.empty:
        for key,g in risk.groupby(["group_id","engine"]):
            v=g[g.status=="ok"];delta=v.get("annualized_volatility_delta",pd.Series(dtype=float))
            stability.append(dict(group_id=key[0],engine=key[1],question="inverse_volatility_lower_risk",
                valid_cases=len(v),unavailable_cases=len(g)-len(v),positive_cases=int((delta<0).sum()),
                minimum=delta.min(),maximum=delta.max(),
                conclusion="consistent_in_available_cases" if len(v) and (delta<0).all() else "mixed_or_unavailable"))
    for key,g in freq[(freq.basis=="net")|(freq.engine=="phase4")].groupby(["group_id","engine","strategy","cost_bps"]):
        v=g[g.status=="ok"];delta=v.get("annualized_return_delta",pd.Series(dtype=float))
        stability.append(dict(group_id=key[0],engine=key[1],strategy=key[2],cost_bps=key[3],
            question="monthly_return_improvement",valid_cases=len(v),unavailable_cases=len(g)-len(v),
            positive_cases=int((delta>1e-12).sum()),minimum=delta.min(),maximum=delta.max(),
            conclusion="monthly_higher_in_available_cases" if len(v) and (delta>1e-12).all()
            else "quarterly_higher_in_available_cases" if len(v) and (delta< -1e-12).all() else "mixed_no_stable_winner"))
    return dict(frequency_comparison=freq,risk_comparison=risk,window_sensitivity=pd.DataFrame(ranges),
                stability_summary=pd.DataFrame(stability))
