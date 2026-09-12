import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.backtest import run_backtest
from portfolio_analysis.index_construction import run_index,rebalance_dates

def sample():
    cal=pd.bdate_range("2022-01-03","2025-02-05")
    dates=cal[cal<="2024-12-31"]
    k=np.arange(len(dates))
    r=pd.DataFrame({"A":.001+.01*np.sin(k),"511010.SS":.0001+.001*np.cos(k)},index=dates)
    universe=[dict(symbol=s,eligible_from="2022-01-03") for s in r]
    return cal,r,universe

def test_explicit_anchor_makes_windows_share_dates_and_cadence():
    cal,r,u=sample()
    results=[run_backtest(r,estimation_window=w,inception_date="2024-03-29") for w in [126,252,504]]
    assert all(x.daily.index.equals(results[0].daily.index) for x in results)
    assert all(x.trades.execution_date.equals(results[0].trades.execution_date) for x in results)
    assert all(x.daily.index[0]==pd.Timestamp("2024-04-01") for x in results)
    # EW has no window-dependent signal, so anchoring removes spurious sensitivity.
    for x in results[1:]:pd.testing.assert_frame_equal(results[0].daily,x.daily)

def test_index_explicit_anchor_and_window_handling():
    cal,r,u=sample()
    a=run_index(r,cal,u,estimation_window=126,inception_date="2024-03-29")
    b=run_index(r,cal,u,estimation_window=504,inception_date="2024-03-29")
    pd.testing.assert_frame_equal(a.daily,b.daily)
    with pytest.raises(ValueError):run_index(r,cal,u,estimation_window=504,inception_date="2022-03-31")
    with pytest.raises(ValueError):run_index(r,cal,u,estimation_window=126,inception_date="2024-03-28")

def test_default_backtest_and_explicit_same_anchor_identical():
    cal,r,u=sample()
    a=run_backtest(r,estimation_window=126,cost_bps=10)
    b=run_backtest(r,estimation_window=126,cost_bps=10,inception_date=r.index[126])
    pd.testing.assert_frame_equal(a.daily,b.daily)
    pd.testing.assert_frame_equal(a.trades,b.trades)

@pytest.mark.parametrize("date",["2022-01-05","2024-03-30","2024-12-31","2024-03-29 12:00"])
def test_bad_backtest_anchor(date):
    cal,r,u=sample()
    with pytest.raises(ValueError):run_backtest(r,estimation_window=126,inception_date=date)

def test_no_lookahead_with_shared_anchor():
    cal,r,u=sample()
    original=run_backtest(r,strategy="inverse_volatility",estimation_window=126,inception_date="2024-03-29")
    cut=original.trades.execution_date.iloc[2]
    changed=r.copy();changed.loc[cut:,"A"]+=.05
    other=run_backtest(changed,strategy="inverse_volatility",estimation_window=126,inception_date="2024-03-29")
    cols=["execution_date","symbol","target_weight"]
    pd.testing.assert_frame_equal(original.targets.loc[original.targets.execution_date<=cut,cols],
                                  other.targets.loc[other.targets.execution_date<=cut,cols])

def small_rules():
    from portfolio_analysis.robustness import load_robustness_rules
    c=load_robustness_rules()
    c["engines"]=["phase2"]
    c["phase2_strategies"]=["equal_weight"]
    c["cost_bps"]=[0]
    c["groups"]=[dict(group_id="test",inception_date="2024-03-29",end_date="2024-12-31",
        periods=[dict(period_id="full",start="2024-04-01",end="2024-12-31"),
                 dict(period_id="late",start="2024-07-01",end="2024-12-31")])]
    return c

def test_matrix_same_dates_and_subperiod_not_reinitialized():
    from portfolio_analysis.robustness import run_robustness
    cal,r,u=sample();c=small_rules()
    tables,meta=run_robustness(r,cal,u,c)
    summary=tables["sensitivity"]
    assert len(summary)==12
    assert set(summary.status)=={"ok"}
    assert summary.groupby("period_id").evaluation_count.nunique().eq(1).all()
    row=summary[(summary.window==126)&(summary.frequency=="monthly")&(summary.period_id=="late")].iloc[0]
    d=tables["daily"].query("scenario_id==@row.scenario_id").set_index("date").loc["2024-07-01":]
    assert row.gross_cumulative_return==pytest.approx((1+d.gross_return).prod()-1)
    # Later slice has no new initial allocation or initial cost.
    assert row.initial_turnover==0 and row.initial_transaction_cost==0

def test_insufficient_history_is_explicit_skip():
    from portfolio_analysis.robustness import run_robustness
    cal,r,u=sample();c=small_rules()
    c["groups"][0].update(inception_date="2022-06-30")
    c["groups"][0]["periods"]=[dict(period_id="full",start="2022-07-01",end="2024-12-31")]
    tables,meta=run_robustness(r,cal,u,c)
    rows=tables["sensitivity"].query("window==504")
    assert set(rows.status)=={"insufficient_history"}
    assert rows.gross_annualized_return.isna().all()
    assert rows.reason.str.contains("504").all()

@pytest.mark.parametrize("windows",[[0],[125],[126,126],[True],[]])
def test_invalid_windows_rejected(windows):
    from portfolio_analysis.robustness import run_robustness
    cal,r,u=sample();c=small_rules();c["windows"]=windows
    with pytest.raises(ValueError):run_robustness(r,cal,u,c)

def test_subperiod_drawdown_resets_wealth_not_holdings():
    from portfolio_analysis.robustness import score_period
    dates=pd.bdate_range("2024-01-02",periods=4)
    daily=pd.DataFrame({"gross_return":[-.5,.5,-.1,.1],"net_return":[-.5,.5,-.1,.1],
        "gross_nav":[.5,.75,.675,.7425],"net_nav":[.5,.75,.675,.7425],
        "transaction_cost":0.,"initial_transaction_cost":0.},index=dates)
    holdings=pd.DataFrame([dict(date=d,symbol="511010.SS",start_weight=1.,pretrade_weight=1.,end_weight=1.) for d in dates])
    trades=pd.DataFrame([dict(execution_date=dates[0]-pd.Timedelta(days=1),initial=True,turnover=1.)])
    targets=pd.DataFrame([dict(execution_date=trades.execution_date[0],symbol="511010.SS",target_weight=1.)])
    row=score_period(daily,holdings,trades,targets,dates[2:],.02,.7,2,True)
    assert row["gross_maximum_drawdown"]==pytest.approx(-.1)
    assert row["gross_cumulative_return"]==pytest.approx(-.01)

def test_requested_endpoint_not_silently_truncated():
    from portfolio_analysis.robustness import run_robustness
    cal,r,u=sample();c=small_rules()
    c["groups"][0]["end_date"]="2025-01-31"
    c["groups"][0]["periods"][0]["end"]="2025-01-31"
    t,m=run_robustness(r,cal,u,c)
    assert set(t["scenarios"].status)=={"insufficient_evaluation"}
    assert t["sensitivity"].evaluation_count.eq(0).all()
    assert t["daily"].empty

def test_score_failure_labelled_without_partial_paths():
    from portfolio_analysis.robustness import run_robustness
    cal,r,u=sample();r=r.rename(columns={"511010.SS":"B"})
    t,m=run_robustness(r,cal,u,small_rules())
    assert set(t["scenarios"].status)=={"failed"}
    assert t["daily"].empty
    assert m["failed_scenarios"]==6

def test_reports_consistency_and_corrupted_dates():
    from portfolio_analysis.robustness import run_robustness
    from portfolio_analysis.robustness_reporting import build_robustness_reports
    cal,r,u=sample();c=small_rules()
    t,m=run_robustness(r,cal,u,c)
    out=build_robustness_reports(t,c)
    assert out["window_sensitivity"].annualized_return_spread.abs().max()==0
    assert len(out["frequency_comparison"])==12
    t["daily"]=t["daily"].iloc[1:]
    with pytest.raises(ValueError,match="Evaluation count"):
        build_robustness_reports(t,c)

def test_real_matrix_and_serialized_output_consistency():
    from portfolio_analysis.robustness import load_robustness_rules
    from portfolio_analysis.robustness_reporting import build_robustness_reports
    from pathlib import Path
    root=Path("output_phase5/tables")
    s=pd.read_csv(root/"sensitivity.csv")
    scenarios=pd.read_csv(root/"scenarios.csv")
    d=pd.read_csv(root/"daily.csv",parse_dates=["date"])
    assert len(scenarios)==168 and scenarios.status.eq("ok").sum()==140
    assert scenarios.status.eq("insufficient_history").sum()==28
    assert len(s)==672 and s.status.eq("ok").sum()==560
    assert set(s.loc[s.status=="ok"].groupby(["group_id","period_id"]).evaluation_count.first())=={207,60,56,91,451,61,243,147}
    ids=scenarios.loc[(scenarios.cost_bps==0)&(scenarios.engine=="phase2")&(scenarios.status=="ok"),"scenario_id"]
    zero=d[d.scenario_id.isin(ids)]
    np.testing.assert_allclose(zero.gross_return,zero.net_return,atol=1e-14,rtol=0)
    # CSV blank reasons must be restored explicitly for report reproduction.
    s["reason"]=s.reason.fillna("")
    reports=build_robustness_reports({"sensitivity":s,"daily":d},load_robustness_rules())
    assert len(reports["stability_summary"])==34
