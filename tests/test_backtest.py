import numpy as np
import pandas as pd
import pytest
from portfolio_analysis.backtest import run_backtest, execute_trade

def sample(n=340):
    rng=np.random.default_rng(15)
    return pd.DataFrame(rng.normal(0.0003,0.01,(n,3)),
        index=pd.bdate_range("2020-01-01",periods=n),columns=["a","b","c"])

@pytest.mark.parametrize("frequency",[21,63])
def test_schedule_and_first_return(frequency):
    r=sample()
    result=run_backtest(r,rebalance_every=frequency)
    assert result.daily.index.equals(r.index[253:])
    assert result.trades.execution_date.tolist()==r.index[list(range(252,len(r)-1,frequency))].tolist()
    for row in result.trades.itertuples():
        assert row.estimation_end<row.execution_date
        assert row.estimation_count==252
    assert result.trades.iloc[0].first_effective_return_date==r.index[253]

@pytest.mark.parametrize("strategy",["equal_weight","minimum_variance","inverse_volatility"])
def test_future_changes_do_not_change_past(strategy):
    r=sample()
    a=run_backtest(r,strategy=strategy)
    changed=r.copy(); changed.iloc[295:]=.07+changed.iloc[295:]*2
    b=run_backtest(changed,strategy=strategy)
    pd.testing.assert_frame_equal(a.daily.loc[:r.index[294]],b.daily.loc[:r.index[294]])
    pd.testing.assert_frame_equal(
        a.weights[a.weights.date<r.index[295]].reset_index(drop=True),
        b.weights[b.weights.date<r.index[295]].reset_index(drop=True))

@pytest.mark.parametrize("strategy",["minimum_variance","inverse_volatility"])
def test_execution_day_return_excluded_from_estimation(strategy):
    r=sample()
    a=run_backtest(r,strategy=strategy)
    changed=r.copy(); changed.iloc[273]=[.4,-.2,.1]
    b=run_backtest(changed,strategy=strategy)
    x=a.targets[a.targets.execution_date==r.index[273]].target_weight
    y=b.targets[b.targets.execution_date==r.index[273]].target_weight
    np.testing.assert_array_equal(x,y)

def test_drift_hand_calculation_and_no_daily_rebalance():
    r=pd.DataFrame([[.01,-.01],[-.01,.01],[0,0],[.1,0],[0,.1],[0,0]],
        index=pd.bdate_range("2020-01-01",periods=6),columns=["a","b"])
    b=run_backtest(r,estimation_window=2,rebalance_every=21)
    np.testing.assert_allclose(b.daily.gross_return,[.05,.05/1.05,0])
    w=b.weights[b.weights.date==r.index[3]].end_weight
    np.testing.assert_allclose(w,[.55/1.05,.5/1.05])
    assert (b.daily.turnover==pd.Series([1.,0.,0.],index=b.daily.index)).all()
    assert b.daily.iloc[1:].transaction_cost.sum()==0

def test_turnover_uses_drifted_holdings():
    r=pd.DataFrame(np.zeros((27,2)),index=pd.bdate_range("2020-01-01",periods=27),columns=["a","b"])
    r.iloc[3]=[1.,0]
    b=run_backtest(r,estimation_window=2,rebalance_every=21)
    second=b.trades.iloc[1]
    assert second.turnover==pytest.approx(1/6)
    np.testing.assert_allclose(b.targets[b.targets.execution_date==r.index[23]].pretrade_weight,[2/3,1/3])

def test_self_financing_cost_and_initial_cash():
    initial=execute_trade(np.zeros(2),np.array([.5,.5]),20)
    assert initial["cost_fraction"]==pytest.approx(.002/1.002)
    assert initial["turnover"]==pytest.approx(1)
    result=execute_trade(np.array([.8,.2]),np.array([.5,.5]),10)
    assert result["turnover"]==pytest.approx(.3)
    assert result["cost_fraction"]==pytest.approx(.0006)
    assert result["buy_fraction"]-result["sell_fraction"]==pytest.approx(-result["cost_fraction"])

@pytest.mark.parametrize("bps",[0,5,10,20])
def test_nav_cost_accounting_and_common_dates(bps):
    r=sample()
    b=run_backtest(r,cost_bps=bps)
    np.testing.assert_allclose((1+b.daily.net_return).cumprod(),b.daily.net_nav)
    np.testing.assert_allclose((1+b.daily.gross_return).cumprod(),b.daily.gross_nav)
    assert b.daily.transaction_cost.sum()==pytest.approx(b.trades.transaction_cost.sum())
    assert b.daily.turnover.sum()==pytest.approx(b.trades.turnover.sum())
    assert b.daily.index.equals(r.index[253:])
    assert (b.daily.net_nav<=b.daily.gross_nav+1e-12).all()
    if bps==0:
        np.testing.assert_array_equal(b.daily.gross_return,b.daily.net_return)
        np.testing.assert_array_equal(b.daily.gross_nav,b.daily.net_nav)
    assert b.daily.iloc[0].initial_transaction_cost==pytest.approx(b.trades.iloc[0].transaction_cost)

@pytest.mark.parametrize("strategy",["equal_weight","minimum_variance","inverse_volatility"])
def test_weights_sum_and_concentration(strategy):
    b=run_backtest(sample(),strategy=strategy)
    sums=b.weights.groupby("date")[["start_weight","pretrade_weight","end_weight"]].sum()
    np.testing.assert_allclose(sums,1,atol=1e-10)
    assert (b.weights[["start_weight","pretrade_weight","end_weight"]]>=0).all().all()
    for date,rows in b.weights.groupby("date"):
        assert b.daily.loc[date,"hhi"]==pytest.approx((rows.end_weight**2).sum())
        assert b.daily.loc[date,"maximum_weight"]==pytest.approx(rows.end_weight.max())

@pytest.mark.parametrize("problem",["nan","unordered","duplicate","short"])
def test_invalid_inputs_fail_without_silent_drop(problem):
    r=sample()
    if problem=="nan": r.iloc[280,0]=np.nan
    if problem=="unordered": r=r.iloc[::-1]
    if problem=="duplicate": r.index=[r.index[0]]*len(r)
    if problem=="short": r=r.iloc[:254]
    with pytest.raises(ValueError):
        run_backtest(r)

def test_optimizer_failure_not_replaced(monkeypatch):
    import portfolio_analysis.backtest as module
    def fail(_): raise ValueError("intentional optimizer failure")
    monkeypatch.setattr(module,"minimum_volatility_weights",fail)
    with pytest.raises(ValueError,match="intentional optimizer failure"):
        module.run_backtest(sample(),strategy="minimum_variance")

def test_initial_fee_changes_first_net_return_exactly():
    r=pd.DataFrame(np.zeros((7,2)),index=pd.bdate_range("2020-01-01",periods=7),columns=["a","b"])
    r.iloc[3]=[.1,0]
    b=run_backtest(r,estimation_window=2,cost_bps=20)
    assert b.daily.iloc[0].gross_return==pytest.approx(.05)
    assert b.daily.iloc[0].net_return==pytest.approx(1.05/1.002-1)
    assert b.daily.iloc[-1].net_nav==pytest.approx(1.05/1.002)
    assert b.trades.iloc[0].execution_date==r.index[2]
    assert b.daily.index[0]==r.index[3]

def test_terminal_rebalance_without_future_return_is_not_executed():
    r=sample(24)
    b=run_backtest(r,estimation_window=2,rebalance_every=21,cost_bps=10)
    assert len(b.trades)==1
    assert b.daily.iloc[-1].transaction_cost==0

def test_actual_trade_deltas_pay_fee_and_reach_target():
    pre=np.array([.77,.20,.03])
    target=np.array([.30,.60,.10])
    result=execute_trade(pre,target,20)
    after=(1-result["cost_fraction"])*target
    delta=after-pre
    assert after.sum()+result["cost_fraction"]==pytest.approx(1)
    assert abs(delta).sum()*.002==pytest.approx(result["cost_fraction"])
    np.testing.assert_allclose(after/after.sum(),target)
