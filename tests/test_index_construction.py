import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.index_construction import (
    rebalance_dates, assumed_availability, assess_eligibility, index_weights,
    run_index, IndexCalculationError, concentration)

def sample():
    cal=pd.bdate_range("2023-01-02","2024-02-05")
    dates=cal[cal<="2023-12-29"]
    x=np.arange(len(dates))
    returns=pd.DataFrame({"A":.001+.01*np.sin(x),"B":.0002+.002*np.cos(x)},index=dates)
    universe=[dict(symbol=s,eligible_from="2023-01-02") for s in returns]
    return cal,returns,universe

def test_calendar_month_quarter_and_incomplete_terminal_month():
    cal=pd.bdate_range("2023-01-02","2023-05-05")
    assert list(rebalance_dates(cal,"2023-01-02","2023-04-15","monthly"))==list(pd.to_datetime(["2023-01-31","2023-02-28","2023-03-31"]))
    assert list(rebalance_dates(cal,"2023-01-02","2023-04-15","quarterly"))==[pd.Timestamp("2023-03-31")]

def test_holiday_month_end():
    cal=pd.bdate_range("2023-01-02","2023-03-02").difference(pd.to_datetime(["2023-01-31"]))
    assert rebalance_dates(cal,"2023-01-02","2023-02-15","monthly")[0]==pd.Timestamp("2023-01-30")

def test_weights_and_unconstrained_inverse_volatility():
    h=pd.DataFrame({"A":[-.01,.01,-.01,.01],"B":[-.0001,.0001,-.0001,.0001]})
    w=index_weights(h,"inverse_volatility")
    assert w.sum()==pytest.approx(1)
    assert w.B==pytest.approx(100/101)
    assert index_weights(h,"equal_weight").tolist()==[.5,.5]
    with pytest.raises(ValueError):index_weights(h.assign(B=0),"inverse_volatility")

def test_point_in_time_eligibility_and_delayed_availability():
    cal,r,u=sample()
    available=assumed_availability(r,cal)
    t=pd.Timestamp("2023-03-31")
    available.loc["2023-03-30","B"]=pd.Timestamp("2023-04-01")
    report=assess_eligibility(r,available,u,t,20)
    assert report.set_index("symbol").loc["A","eligible"]
    assert not report.set_index("symbol").loc["B","eligible"]
    assert "not_available_at_decision" in report.set_index("symbol").loc["B","reason"]

def test_membership_effective_date():
    cal,r,u=sample();u[1]["eligible_from"]="2023-04-01"
    a=assess_eligibility(r,assumed_availability(r,cal),u,pd.Timestamp("2023-03-31"),20)
    assert not a.set_index("symbol").loc["B","eligible"]

def test_no_lookahead_and_no_same_day_signal():
    cal,r,u=sample()
    base=run_index(r,cal,u,strategy="inverse_volatility",frequency="monthly",estimation_window=20)
    changed=r.copy();changed.loc["2023-04-28":,"A"]+=.1
    other=run_index(changed,cal,u,strategy="inverse_volatility",frequency="monthly",estimation_window=20)
    before=base.targets[base.targets.execution_date<="2023-04-28"].reset_index(drop=True)
    after=other.targets[other.targets.execution_date<="2023-04-28"].reset_index(drop=True)
    pd.testing.assert_frame_equal(before[["execution_date","symbol","target_weight"]],after[["execution_date","symbol","target_weight"]])
    assert (base.rebalances.estimation_end<base.rebalances.execution_date).all()
    assert (base.rebalances.first_effective_return_date>base.rebalances.execution_date).all()

def test_common_inception_and_true_rebalance_timing():
    cal,r,u=sample()
    a=run_index(r,cal,u,frequency="monthly",estimation_window=20)
    b=run_index(r,cal,u,frequency="quarterly",estimation_window=20)
    assert a.daily.index.equals(b.daily.index)
    assert a.daily.index[0]==pd.Timestamp("2023-03-31")
    assert a.daily.iloc[0].index_level==1000
    assert pd.isna(a.daily.iloc[0].index_return)
    assert a.daily.index[1]==pd.Timestamp("2023-04-03")
    # No terminal rebalance with no subsequent return.
    assert list(b.rebalances.execution_date)==list(pd.to_datetime(["2023-03-31","2023-06-30","2023-09-29"]))

def test_nav_drift_turnover_and_concentration_hand_calculation():
    cal,r,u=sample();r.loc[:,:]=0.
    r.loc["2023-04-03","A"]=.1
    a=run_index(r,cal,u,estimation_window=20)
    assert a.daily.loc["2023-04-03","index_level"]==pytest.approx(1050)
    h=a.holdings.set_index(["date","symbol"])
    assert h.loc[(pd.Timestamp("2023-04-03"),"A"),"end_weight"]==pytest.approx(11/21)
    assert a.daily.loc["2023-04-03","hhi"]==pytest.approx((11/21)**2+(10/21)**2)
    april=a.rebalances.set_index("execution_date").loc["2023-04-28"]
    assert april.turnover==pytest.approx(1/42)
    assert a.rebalances.iloc[0].turnover==pytest.approx(1)
    assert a.daily.loc["2023-04-04","index_return"]==0
    assert np.allclose(a.holdings.groupby("date").end_weight.sum(),1)

def test_missing_history_eligibility_not_silent_drop():
    cal,r,u=sample();r.loc["2023-03-20","B"]=np.nan
    a=run_index(r,cal,u,estimation_window=20)
    first=a.eligibility[a.eligibility.execution_date=="2023-03-31"].set_index("symbol")
    assert not first.loc["B","eligible"]
    assert "missing_history" in first.loc["B","reason"]
    assert a.targets[a.targets.execution_date=="2023-03-31"].set_index("symbol").loc["A","target_weight"]==1

def test_missing_held_return_stops_with_diagnostic():
    cal,r,u=sample();r.loc["2023-04-10","A"]=np.nan
    with pytest.raises(IndexCalculationError) as caught:run_index(r,cal,u,estimation_window=20)
    assert caught.value.diagnostics["date"]=="2023-04-10"
    assert "A" in caught.value.diagnostics["affected_assets"]
    assert caught.value.partial.daily.index[-1]==pd.Timestamp("2023-04-07")

def test_all_ineligible_fails_not_fallback():
    cal,r,u=sample();r.loc["2023-03-20",:]=np.nan
    with pytest.raises(IndexCalculationError,match="No eligible"):run_index(r,cal,u,estimation_window=20)

def test_missing_calendar_row_rejected():
    cal,r,u=sample()
    with pytest.raises(ValueError,match="calendar"):run_index(r.drop(r.index[10]),cal,u,estimation_window=20)

@pytest.mark.parametrize("weights",[[.2,.2],[-.1,1.1],[np.nan,1]])
def test_invalid_concentration_weights(weights):
    with pytest.raises(ValueError):concentration(weights)

def test_concentration_exact():
    assert concentration([.2]*5)==pytest.approx({"maximum_weight":.2,"hhi":.2})

@pytest.mark.parametrize("seconds,expected",[(0,True),(1,False)])
def test_exact_information_cutoff(seconds,expected):
    cal,r,u=sample();a=assumed_availability(r,cal)
    a.loc["2023-03-30","B"]=pd.Timestamp("2023-03-31 14:59")+pd.Timedelta(seconds=seconds)
    report=assess_eligibility(r,a,u,pd.Timestamp("2023-03-31"),20)
    assert bool(report.set_index("symbol").loc["B","eligible"]) is expected

def test_missing_unheld_asset_does_not_abort():
    cal,r,u=sample();u[1]["eligible_from"]="2024-01-01"
    r.loc["2023-04-10","B"]=np.nan
    result=run_index(r,cal,u,estimation_window=20)
    assert result.metadata["status"]=="complete"
    assert result.holdings.query("symbol=='B'").end_weight.eq(0).all()

def test_missing_target_execution_valuation_stops():
    cal,r,u=sample();r.loc["2023-03-31","A"]=np.nan
    with pytest.raises(IndexCalculationError,match="execution-date") as caught:
        run_index(r,cal,u,estimation_window=20)
    assert caught.value.partial.daily.empty

def test_missing_held_on_rebalance_not_liquidated_silently():
    cal,r,u=sample();r.loc["2023-04-28","A"]=np.nan
    with pytest.raises(IndexCalculationError,match="held-asset") as caught:
        run_index(r,cal,u,estimation_window=20)
    assert caught.value.partial.rebalances.execution_date.max()==pd.Timestamp("2023-03-31")
